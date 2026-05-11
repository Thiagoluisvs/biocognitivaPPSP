"""BiocognitivaPPSP - Main App — release 2.0"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os, json, random
from datetime import datetime
from models import get_db, init_db, seed_demo_data

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'biocognitiva-ppsp-2026'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
ALLOWED_EXT = {'pdf','doc','docx','xls','xlsx','ppt','pptx','jpg','jpeg','png','mp4','zip'}

MOTIVO_AGENDAMENTO_LABELS = {
    'exame_admissional': 'Exame admissional',
    'exame_aleatorio': 'Exame aleatório',
    'exame_pos_acidente': 'Exame pós-acidente',
    'exame_retorno_servico': 'Exame de retorno ao serviço',
    'exame_acompanhamento': 'Exame de acompanhamento',
}
MOTIVOS_AGENDAMENTO_VALIDOS = frozenset(MOTIVO_AGENDAMENTO_LABELS.keys())
TIPOS_EXAME_AGENDAMENTO = (
    ('toxicologico_urina', 'Toxicológico urina'),
    ('toxicologico_queratina', 'Toxicológico queratina'),
    ('alcoolemia', 'Alcolemia'),
)
TIPOS_EXAME_VALIDOS = frozenset(t[0] for t in TIPOS_EXAME_AGENDAMENTO)
_EXAME_ORDER = {t[0]: i for i, t in enumerate(TIPOS_EXAME_AGENDAMENTO)}
TIPO_EVENTO_LABELS = {
    'positivo_amostra': 'Amostra positiva / laboratorial',
    'agendamento_avaliacao_psicologica': 'Agendamento — Avaliação psicológica',
    'agendamento_medico_revisor': 'Agendamento — Médico revisor',
}


@app.template_filter('exames_json_list')
def exames_json_list(s):
    try:
        return json.loads(s) if s else []
    except (json.JSONDecodeError, TypeError):
        return []


@app.template_filter('label_exame_agendamento')
def label_exame_agendamento(code):
    return dict(TIPOS_EXAME_AGENDAMENTO).get(code, (code or '').replace('_', ' ').title())


@app.template_filter('label_motivo_agendamento')
def label_motivo_agendamento(code):
    return MOTIVO_AGENDAMENTO_LABELS.get(code, (code or '').replace('_', ' ').title())


@app.template_filter('label_evento_impeditivo')
def label_evento_impeditivo(code):
    return TIPO_EVENTO_LABELS.get(code, (code or '').replace('_', ' ').title())


@app.context_processor
def inject_release():
    return {
        'motivos_agendamento': MOTIVO_AGENDAMENTO_LABELS,
        'tipos_exame_agendamento': TIPOS_EXAME_AGENDAMENTO,
        'app_release': '2.0',
    }


def allowed_file(f):
    return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXT

def login_required(f):
    @wraps(f)
    def dec(*a,**k):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a,**k)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a,**k):
            if 'user_id' not in session: return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('Acesso não autorizado.','error')
                return redirect(url_for('dashboard'))
            return f(*a,**k)
        return dec
    return decorator

def get_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    u = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    db.close()
    return u

@app.before_request
def _local_debug_institucional_session():
    """Em debug, acessos de localhost a /institucional* entram com o primeiro usuário ADM ativo (só para teste local)."""
    if not app.debug or session.get('user_id'):
        return
    if not request.path.startswith('/institucional'):
        return
    host = (request.host or '').split(':')[0].lower()
    addr = (request.environ.get('REMOTE_ADDR') or '').lower()
    if host not in ('127.0.0.1', 'localhost') and addr not in ('127.0.0.1', '::1'):
        return
    db = get_db()
    row = db.execute(
        """SELECT id, name, role FROM users WHERE active=1
           AND role IN ('administrador','adm_biocognitiva','supervisor','tecnico')
           ORDER BY CASE role WHEN 'administrador' THEN 0 WHEN 'adm_biocognitiva' THEN 1 ELSE 2 END, id LIMIT 1"""
    ).fetchone()
    db.close()
    if row:
        session['user_id'] = row['id']
        session['name'] = row['name']
        session['role'] = row['role']

def log_audit(user_id, action, entity_type, entity_id, old_values=None, new_values=None, changes=None):
    """Registra operações de auditoria no banco de dados"""
    db = get_db()
    db.execute('''INSERT INTO audit_log (user_id, action, entity_type, entity_id, old_values, new_values, changes)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (user_id, action, entity_type, entity_id, 
         json.dumps(old_values or {}), 
         json.dumps(new_values or {}),
         changes or ''))
    db.commit()
    db.close()

def get_field_changes(old_dict, new_dict):
    """Retorna resumo das mudanças entre dois dicionários"""
    changes = []
    for key in set(list((old_dict or {}).keys()) + list((new_dict or {}).keys())):
        old_val = (old_dict or {}).get(key, '')
        new_val = (new_dict or {}).get(key, '')
        if old_val != new_val:
            changes.append(f"{key}: '{old_val}' → '{new_val}'")
    return '; '.join(changes)


@app.route('/documentos/<path:filename>')
@login_required
def serve_document(filename):
    base = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'))
    safe = secure_filename(os.path.basename(filename))
    if not safe:
        abort(404)
    full = os.path.abspath(os.path.join(base, safe))
    if not full.startswith(base) or not os.path.isfile(full):
        abort(404)
    return send_from_directory(base, safe, as_attachment=False)


def save_upload(file, subfolder='documents'):
    fn=secure_filename(file.filename); ts=datetime.now().strftime('%Y%m%d%H%M%S')
    saved=f"{ts}_{fn}"; path=os.path.join(app.config['UPLOAD_FOLDER'],subfolder,saved)
    os.makedirs(os.path.dirname(path),exist_ok=True); file.save(path)
    return saved, fn, os.path.getsize(path)

@app.errorhandler(sqlite3.Error)
def handle_db_error(e):
    flash(f"Erro de Banco de Dados: {e}", "error")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if 'user_id' in session else redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        db=get_db(); u=db.execute('SELECT * FROM users WHERE email=?',(request.form.get('email',''),)).fetchone(); db.close()
        if u and check_password_hash(u['password_hash'], request.form.get('password','')):
            session['user_id']=u['id']; session['role']=u['role']; session['name']=u['name']
            return redirect(url_for('dashboard'))
        flash('Email ou senha incorretos.','error')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        n=request.form.get('name',''); e=request.form.get('email',''); p=request.form.get('password','')
        db=get_db()
        if db.execute('SELECT id FROM users WHERE email=?',(e,)).fetchone():
            db.close(); flash('Email já cadastrado.','error'); return render_template('register.html')
        db.execute('INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)',
            (n,e,generate_password_hash(p,method='pbkdf2:sha256'),'colaborador'))
        db.commit(); u=db.execute('SELECT * FROM users WHERE email=?',(e,)).fetchone(); db.close()
        session['user_id']=u['id']; session['role']=u['role']; session['name']=u['name']
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    u = get_user()
    if not u:
        session.clear()
        return redirect(url_for('login'))
    
    db = get_db()
    d = {}
    
    try:
        if u['role'] == 'colaborador':
            colab = db.execute('SELECT * FROM colaboradores WHERE email=?', (u['email'],)).fetchone()
            d['colab'] = colab
            d['videos'] = db.execute('SELECT * FROM video_aulas ORDER BY ordem').fetchall()
            d['avaliacoes'] = db.execute('SELECT * FROM avaliacoes WHERE active=1').fetchall()
            if colab:
                d['tentativas'] = db.execute('SELECT * FROM avaliacao_tentativas WHERE colaborador_id=? ORDER BY completed_at DESC', (colab['id'],)).fetchall()
        
        elif u['role'] == 'supervisor':
            d['total_colabs'] = db.execute('SELECT COUNT(*) as c FROM colaboradores').fetchone()['c']
            d['total_agend'] = db.execute('SELECT COUNT(*) as c FROM agendamentos').fetchone()['c']
            d['agenda_hoje'] = db.execute("SELECT a.*, c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id WHERE a.data_coleta=date('now') ORDER BY a.horario_coleta").fetchall()
            d['agendamentos'] = db.execute('SELECT a.*, c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id ORDER BY a.data_coleta DESC LIMIT 10').fetchall()
            
        elif u['role'] in ['tecnico', 'tecnico_biocognitiva']:
            d['total_agend'] = db.execute('SELECT COUNT(*) as c FROM agendamentos').fetchone()['c']
            d['total_resultados'] = db.execute('SELECT COUNT(*) as c FROM resultados_exames').fetchone()['c']
            d['agenda_hoje'] = db.execute("SELECT a.*, c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id WHERE a.data_coleta=date('now') ORDER BY a.horario_coleta").fetchall()
            d['agendamentos'] = db.execute('SELECT a.*, c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id ORDER BY a.data_coleta DESC LIMIT 10').fetchall()
            
        elif u['role'] in ['adm_biocognitiva', 'administrador']:
            d['total_users'] = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
            d['total_colabs'] = db.execute('SELECT COUNT(*) as c FROM colaboradores').fetchone()['c']
            d['total_agend'] = db.execute('SELECT COUNT(*) as c FROM agendamentos').fetchone()['c']
            d['total_resultados'] = db.execute('SELECT COUNT(*) as c FROM resultados_exames').fetchone()['c']
            d['users'] = db.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 5').fetchall()
            d['agendamentos'] = db.execute('SELECT a.*, c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id ORDER BY a.data_coleta DESC LIMIT 10').fetchall()
    except Exception as e:
        print(f"Dashboard Data Fetch Error: {e}")
        d['error_msg'] = "Alguns dados não puderam ser carregados no momento."

    db.close()
    return render_template('dashboard.html', user=u, data=d)

@app.route('/export/<type>')
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def export_csv(type):
    import io, csv
    from flask import Response
    db = get_db()
    output = io.StringIO()
    writer = csv.writer(output)
    
    if type == 'colaboradores':
        rows = db.execute('SELECT * FROM colaboradores').fetchall()
        writer.writerow(['Nome', 'CPF', 'Função', 'Empresa', 'Status', 'Telefone', 'Email'])
        for r in rows:
            writer.writerow([r['name'], r['cpf'], r['funcao'], r['empresa'], r['status'], r['telefone'], r['email']])
        filename = "colaboradores.csv"
    elif type == 'agendamentos':
        rows = db.execute('SELECT a.*, c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id').fetchall()
        writer.writerow(['Colaborador', 'Motivo', 'Data', 'Hora', 'Local', 'Status'])
        for r in rows:
            writer.writerow([r['colab_name'], r['motivo'], r['data_coleta'], r['horario_coleta'], r['local_coleta'], r['status']])
        filename = "agendamentos.csv"
    else:
        return abort(404)
        
    db.close()
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

# === COLABORADORES CRUD ===
@app.route('/colaboradores')
@login_required
def colaboradores():
    u=get_user(); db=get_db()
    colabs=db.execute('SELECT * FROM colaboradores ORDER BY name').fetchall(); db.close()
    return render_template('colaboradores.html', user=u, colaboradores=colabs)

@app.route('/colaborador/novo', methods=['GET','POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def colaborador_novo():
    u=get_user()
    if request.method=='POST':
        name=(request.form.get('name') or '').strip()
        cpf=(request.form.get('cpf') or '').strip()
        tel=(request.form.get('telefone') or '').strip()
        if not name:
            flash('Nome é obrigatório.','error')
            return render_template('colaborador_form.html', user=u, colab=None)
        if not cpf:
            flash('CPF é obrigatório.','error')
            return render_template('colaborador_form.html', user=u, colab=None)
        if not tel:
            flash('Telefone é obrigatório.','error')
            return render_template('colaborador_form.html', user=u, colab=None)
        db=get_db()
        cursor = db.execute('''INSERT INTO colaboradores (name,cpf,endereco,funcao,data_admissao,telefone,email,empresa,registered_by)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (name,cpf,request.form.get('endereco',''),
             request.form.get('funcao','ARSO'),request.form.get('data_admissao',''),
             tel,request.form.get('email',''),
             request.form.get('empresa',''),u['id']))
        db.commit()
        new_colab_id = cursor.lastrowid
        new_values = {
            'name': name, 'cpf': cpf, 'endereco': request.form.get('endereco',''),
            'funcao': request.form.get('funcao','ARSO'), 'telefone': tel,
            'email': request.form.get('email',''), 'empresa': request.form.get('empresa','')
        }
        log_audit(u['id'], 'CREATE', 'colaboradores', new_colab_id, old_values={}, new_values=new_values)
        db.close()
        flash('Colaborador cadastrado!','success')
        return redirect(url_for('colaboradores'))
    return render_template('colaborador_form.html', user=u, colab=None)

@app.route('/colaborador/<int:id>/editar', methods=['GET','POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def colaborador_editar(id):
    u=get_user(); db=get_db()
    colab=db.execute('SELECT * FROM colaboradores WHERE id=?',(id,)).fetchone()
    if not colab: db.close(); flash('Colaborador não encontrado.','error'); return redirect(url_for('colaboradores'))
    
    if request.method=='POST':
        name=(request.form.get('name') or '').strip()
        cpf=(request.form.get('cpf') or '').strip()
        tel=(request.form.get('telefone') or '').strip()
        if not name:
            flash('Nome é obrigatório.','error')
            return render_template('colaborador_form.html', user=u, colab=colab)
        if not cpf:
            flash('CPF é obrigatório.','error')
            return render_template('colaborador_form.html', user=u, colab=colab)
        if not tel:
            flash('Telefone é obrigatório.','error')
            return render_template('colaborador_form.html', user=u, colab=colab)
        
        # Valores antigos para auditoria
        old_values = dict(colab)
        db.execute('''UPDATE colaboradores SET name=?, cpf=?, endereco=?, funcao=?, data_admissao=?, telefone=?, email=?, empresa=?, status=?, updated_at=CURRENT_TIMESTAMP, updated_by=?
            WHERE id=?''',
            (name, cpf, request.form.get('endereco',''),
             request.form.get('funcao',''), request.form.get('data_admissao',''),
             tel, request.form.get('email',''),
             request.form.get('empresa',''), request.form.get('status','ativo'), u['id'], id))
        
        # Valores novos para auditoria
        new_values = {
            'name': name, 'cpf': cpf, 'endereco': request.form.get('endereco',''),
            'funcao': request.form.get('funcao',''), 'telefone': tel,
            'email': request.form.get('email',''), 'empresa': request.form.get('empresa',''),
            'status': request.form.get('status','ativo')
        }
        
        changes = get_field_changes(old_values, new_values)
        log_audit(u['id'], 'UPDATE', 'colaboradores', id, old_values=old_values, new_values=new_values, changes=changes)
        db.commit(); db.close(); flash('Colaborador atualizado!','success')
        return redirect(url_for('colaboradores'))
    
    db.close()
    return render_template('colaborador_form.html', user=u, colab=colab)

@app.route('/colaborador/<int:id>/excluir')
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def colaborador_excluir(id):
    u=get_user()
    db=get_db()
    try:
        colab=db.execute('SELECT * FROM colaboradores WHERE id=?',(id,)).fetchone()
        if colab:
            old_values = dict(colab)
            _delete_colaborador_dependencies(db, id)
            db.execute('DELETE FROM colaboradores WHERE id=?',(id,))
            log_audit(u['id'], 'DELETE', 'colaboradores', id, old_values=old_values, new_values={})
            db.commit()
            flash('Colaborador e dados vinculados excluídos com sucesso.','success')
        else:
            flash('Colaborador não encontrado.','error')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao excluir colaborador: {e}','error')
    finally:
        db.close()
    return redirect(url_for('colaboradores'))

@app.route('/colaborador/<int:id>/duplicar')
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def colaborador_duplicar(id):
    db=get_db()
    c=db.execute('SELECT * FROM colaboradores WHERE id=?',(id,)).fetchone()
    if c:
        db.execute('''INSERT INTO colaboradores (name,cpf,endereco,funcao,data_admissao,telefone,email,empresa,registered_by)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (c['name'] + ' (Cópia)', c['cpf'], c['endereco'], c['funcao'], c['data_admissao'], c['telefone'], c['email'], c['empresa'], get_user()['id']))
        db.commit()
        flash('Colaborador duplicado!','success')
    db.close()
    return redirect(url_for('colaboradores'))

def _unlink_upload_doc(filename):
    if not filename:
        return
    base = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'))
    safe = secure_filename(os.path.basename(filename))
    if not safe:
        return
    full = os.path.abspath(os.path.join(base, safe))
    if full.startswith(base) and os.path.isfile(full):
        try:
            os.remove(full)
        except OSError:
            pass


def _delete_colaborador_dependencies(db, cid):
    """Remove todas as dependências de um colaborador antes de excluí-lo"""
    # 1. Agendamentos e suas dependências
    agends = db.execute('SELECT id FROM agendamentos WHERE colaborador_id=?', (cid,)).fetchall()
    for a in agends:
        _delete_agendamento_dependencies(db, a['id'])
    db.execute('DELETE FROM agendamentos WHERE colaborador_id=?', (cid,))
    
    # 2. Outras tabelas diretas
    db.execute('DELETE FROM treinamentos WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM resultados_exames WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM avaliacao_tentativas WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM faltas WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM controle_positivo WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM rastreabilidade WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM prontuarios WHERE colaborador_id=?', (cid,))
    db.execute('DELETE FROM video_progresso WHERE colaborador_id=?', (cid,))


def _delete_agendamento_dependencies(db, aid):
    """Remove dependências de um agendamento (FKs)"""
    db.execute('UPDATE resultados_exames SET agendamento_id=NULL WHERE agendamento_id=?', (aid,))
    db.execute('UPDATE faltas SET agendamento_id=NULL WHERE agendamento_id=?', (aid,))
    db.execute('UPDATE controle_positivo SET resultado_id=NULL WHERE resultado_id IN (SELECT id FROM resultados_exames WHERE agendamento_id=?)', (aid,))


def _bulk_duplicate_entity(db, entity, eid, uid):
    eid = int(eid)
    if entity == 'colaborador':
        c = db.execute('SELECT * FROM colaboradores WHERE id=?', (eid,)).fetchone()
        if c:
            db.execute(
                '''INSERT INTO colaboradores (name,cpf,endereco,funcao,data_admissao,telefone,email,empresa,registered_by)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (c['name'] + ' (Cópia)', c['cpf'], c['endereco'], c['funcao'], c['data_admissao'], c['telefone'], c['email'], c['empresa'], uid),
            )
        return
    if entity == 'agendamento':
        a = db.execute('SELECT * FROM agendamentos WHERE id=?', (eid,)).fetchone()
        if a:
            db.execute(
                '''INSERT INTO agendamentos (colaborador_id,motivo,data_coleta,horario_coleta,local_coleta,exames,agendado_por)
                VALUES (?,?,?,?,?,?,?)''',
                (a['colaborador_id'], a['motivo'], a['data_coleta'], a['horario_coleta'], a['local_coleta'], a['exames'], uid),
            )
        return
    if entity == 'treinamento':
        t = db.execute('SELECT * FROM treinamentos WHERE id=?', (eid,)).fetchone()
        if t:
            db.execute(
                '''INSERT INTO treinamentos (colaborador_id,titulo,motivo,tipo,data_treinamento,horario,arquivo_gravacao,status,agendado_por)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (t['colaborador_id'], (t['titulo'] or '') + ' (Cópia)', t['motivo'], t['tipo'], t['data_treinamento'], t['horario'], t['arquivo_gravacao'], (t['status'] if t['status'] else 'agendado'), uid),
            )
        return
    if entity == 'resultado':
        r = db.execute('SELECT * FROM resultados_exames WHERE id=?', (eid,)).fetchone()
        if r:
            db.execute(
                '''INSERT INTO resultados_exames (colaborador_id,agendamento_id,data_coleta,resultado,observacao,
                foto_doador,foto_bafometro,foto_termo_consentimento,foto_documento,arquivo_resultado,lancado_por)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    r['colaborador_id'],
                    r['agendamento_id'],
                    r['data_coleta'],
                    r['resultado'],
                    r['observacao'],
                    r['foto_doador'],
                    r['foto_bafometro'],
                    r['foto_termo_consentimento'],
                    r['foto_documento'],
                    r['arquivo_resultado'],
                    uid,
                ),
            )
        return
    if entity == 'relatorio':
        r = db.execute('SELECT * FROM relatorios WHERE id=?', (eid,)).fetchone()
        if r:
            db.execute(
                'INSERT INTO relatorios (titulo,descricao,categoria,filename,original_filename,file_size,uploaded_by) VALUES (?,?,?,?,?,?,?)',
                ((r['titulo'] or '') + ' (Cópia)', r['descricao'], r.get('categoria') or 'geral', r['filename'], r['original_filename'], r['file_size'], uid),
            )
        return
    if entity == 'servico':
        s = db.execute('SELECT * FROM servicos WHERE id=?', (eid,)).fetchone()
        if s:
            db.execute(
                'INSERT INTO servicos (tipo,titulo,descricao,documento_anexo,documento_resposta,status,solicitado_por) VALUES (?,?,?,?,?,?,?)',
                (s['tipo'], (s['titulo'] or '') + ' (Cópia)', s['descricao'], s['documento_anexo'], s.get('documento_resposta') or '', 'pendente', uid),
            )
        return
    if entity == 'sorteio':
        s = db.execute('SELECT * FROM sorteios WHERE id=?', (eid,)).fetchone()
        if s:
            db.execute(
                'INSERT INTO sorteios (titulo,quantidade,colaboradores_sorteados,realizado_por) VALUES (?,?,?,?)',
                ((s['titulo'] or '') + ' (Cópia)', s['quantidade'], s['colaboradores_sorteados'], uid),
            )
        return
    if entity == 'falta':
        f = db.execute('SELECT * FROM faltas WHERE id=?', (eid,)).fetchone()
        if f:
            db.execute(
                'INSERT INTO faltas (colaborador_id,data_falta,agendamento_id,observacao,registrado_por) VALUES (?,?,?,?,?)',
                (f['colaborador_id'], f['data_falta'], f['agendamento_id'], f['observacao'], uid),
            )
        return
    if entity == 'controle_positivo':
        cp = db.execute('SELECT * FROM controle_positivo WHERE id=?', (eid,)).fetchone()
        if cp:
            db.execute(
                '''INSERT INTO controle_positivo (colaborador_id,resultado_id,tipo_evento,data_agendamento,horario_agendamento,
                info_amostra,remessa_correio,arquivo_resultado,observacao,registrado_por) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (
                    cp['colaborador_id'],
                    cp['resultado_id'],
                    cp['tipo_evento'],
                    cp['data_agendamento'],
                    cp['horario_agendamento'],
                    cp['info_amostra'],
                    cp['remessa_correio'],
                    cp['arquivo_resultado'],
                    cp['observacao'],
                    uid,
                ),
            )
        return
    if entity == 'cliente':
        c = db.execute('SELECT * FROM clientes_empresa WHERE id=?', (eid,)).fetchone()
        if c:
            db.execute(
                '''INSERT INTO clientes_empresa (razao_social,nome_fantasia,cnpj,cidade,contato_nome,telefone,email,observacao,registered_by)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                ((c['razao_social'] or '') + ' (Cópia)', c['nome_fantasia'], c['cnpj'], c['cidade'], c['contato_nome'], c['telefone'], c['email'], c['observacao'], uid),
            )
        return
    if entity == 'subcontratada':
        s = db.execute('SELECT * FROM subcontratadas WHERE id=?', (eid,)).fetchone()
        if s:
            db.execute(
                '''INSERT INTO subcontratadas (nome_fantasia,razao_social,cnpj,contato_nome,telefone,email,observacao,registered_by)
                VALUES (?,?,?,?,?,?,?,?)''',
                ((s['nome_fantasia'] or '') + ' (Cópia)', s['razao_social'], s['cnpj'], s['contato_nome'], s['telefone'], s['email'], s['observacao'], uid),
            )
        return
    if entity == 'financeiro':
        d = db.execute('SELECT * FROM financeiro WHERE id=?', (eid,)).fetchone()
        if d:
            db.execute(
                'INSERT INTO financeiro (tipo,titulo,descricao,filename,original_filename,file_size,uploaded_by) VALUES (?,?,?,?,?,?,?)',
                (d['tipo'], (d['titulo'] or '') + ' (Cópia)', d['descricao'], d['filename'], d['original_filename'], d['file_size'], uid),
            )


@app.route('/bulk-action/<action>', methods=['POST'])
@login_required
def bulk_action(action):
    entity = (request.form.get('entity') or 'colaborador').strip()
    ids = json.loads(request.form.get('ids', '[]'))
    role = session.get('role')
    if not ids:
        flash('Nenhum item selecionado.', 'warning')
        return redirect(request.referrer or url_for('dashboard'))

    BULK_PERMS = {
        'colaborador': ('supervisor', 'adm_biocognitiva', 'administrador'),
        'agendamento': ('supervisor', 'adm_biocognitiva', 'administrador'),
        'treinamento': ('supervisor', 'adm_biocognitiva', 'administrador'),
        'resultado': ('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador'),
        'relatorio': ('adm_biocognitiva', 'administrador'),
        'servico': ('supervisor', 'adm_biocognitiva', 'administrador'),
        'sorteio': ('supervisor', 'adm_biocognitiva', 'administrador'),
        'falta': ('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador'),
        'controle_positivo': ('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador'),
        'cliente': ('adm_biocognitiva', 'administrador'),
        'subcontratada': ('supervisor', 'adm_biocognitiva', 'administrador'),
        'financeiro': ('adm_biocognitiva', 'administrador'),
    }
    if entity not in BULK_PERMS or role not in BULK_PERMS[entity]:
        flash('Sem permissão para esta ação em massa.', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    uid = get_user()['id']
    db = get_db()
    try:
        if action == 'excluir':
            for i in ids:
                i = int(i)
                if entity == 'colaborador':
                    _delete_colaborador_dependencies(db, i)
                    db.execute('DELETE FROM colaboradores WHERE id=?', (i,))
                elif entity == 'agendamento':
                    _delete_agendamento_dependencies(db, i)
                    db.execute('DELETE FROM agendamentos WHERE id=?', (i,))
                elif entity == 'treinamento':
                    tr = db.execute('SELECT arquivo_gravacao FROM treinamentos WHERE id=?', (i,)).fetchone()
                    if tr and tr['arquivo_gravacao']:
                        _unlink_upload_doc(tr['arquivo_gravacao'])
                    db.execute('DELETE FROM treinamentos WHERE id=?', (i,))
                elif entity == 'resultado':
                    r = db.execute(
                        'SELECT foto_doador,foto_bafometro,foto_termo_consentimento,foto_documento,arquivo_resultado FROM resultados_exames WHERE id=?',
                        (i,),
                    ).fetchone()
                    if r:
                        for fn in (
                            r['foto_doador'],
                            r['foto_bafometro'],
                            r['foto_termo_consentimento'],
                            r['foto_documento'],
                            r['arquivo_resultado'],
                        ):
                            _unlink_upload_doc(fn or '')
                    db.execute('DELETE FROM resultados_exames WHERE id=?', (i,))
                elif entity == 'relatorio':
                    row = db.execute('SELECT filename FROM relatorios WHERE id=?', (i,)).fetchone()
                    if row and row['filename']:
                        _unlink_upload_doc(row['filename'])
                    db.execute('DELETE FROM relatorios WHERE id=?', (i,))
                elif entity == 'servico':
                    s = db.execute('SELECT documento_anexo,documento_resposta FROM servicos WHERE id=?', (i,)).fetchone()
                    if s:
                        _unlink_upload_doc(s['documento_anexo'])
                        _unlink_upload_doc(s['documento_resposta'] or '')
                    db.execute('DELETE FROM servicos WHERE id=?', (i,))
                elif entity == 'sorteio':
                    db.execute('DELETE FROM sorteios WHERE id=?', (i,))
                elif entity == 'falta':
                    db.execute('DELETE FROM faltas WHERE id=?', (i,))
                elif entity == 'controle_positivo':
                    cp = db.execute('SELECT arquivo_resultado FROM controle_positivo WHERE id=?', (i,)).fetchone()
                    if cp and cp['arquivo_resultado']:
                        _unlink_upload_doc(cp['arquivo_resultado'])
                    db.execute('DELETE FROM controle_positivo WHERE id=?', (i,))
                elif entity == 'cliente':
                    db.execute('DELETE FROM clientes_empresa WHERE id=?', (i,))
                elif entity == 'subcontratada':
                    db.execute('DELETE FROM subcontratadas WHERE id=?', (i,))
                elif entity == 'financeiro':
                    row = db.execute('SELECT filename FROM financeiro WHERE id=?', (i,)).fetchone()
                    if row and row['filename']:
                        _unlink_upload_doc(row['filename'])
                    db.execute('DELETE FROM financeiro WHERE id=?', (i,))
            flash(f'{len(ids)} itens excluídos.', 'success')
        elif action == 'duplicar':
            for i in ids:
                _bulk_duplicate_entity(db, entity, i, uid)
            flash(f'{len(ids)} itens duplicados.', 'success')
        elif action == 'editar':
            flash('Para editar, use o ícone de lápis na linha (edição em massa genérica não está disponível).', 'info')
        db.commit()
    except Exception as ex:
        db.rollback()
        flash(f'Erro na operação em massa: {ex}', 'error')
    finally:
        db.close()
    return redirect(request.referrer or url_for('dashboard'))

# === AUDITORIA ===
@app.route('/auditoria')
@login_required
@role_required('adm_biocognitiva','administrador')
def auditoria():
    u=get_user(); db=get_db()
    
    # Filtros
    entity_type = request.args.get('entity_type', '')
    action = request.args.get('action', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    # Query base
    query = 'SELECT a.*, u.name as user_name FROM audit_log a JOIN users u ON a.user_id=u.id WHERE 1=1'
    count_query = 'SELECT COUNT(*) as c FROM audit_log a JOIN users u ON a.user_id=u.id WHERE 1=1'
    params = []
    
    if entity_type:
        query += ' AND a.entity_type=?'
        count_query += ' AND a.entity_type=?'
        params.append(entity_type)
    
    if action:
        query += ' AND a.action=?'
        count_query += ' AND a.action=?'
        params.append(action)
    
    # Total registros
    count = db.execute(count_query, params).fetchone()['c']
    
    # Registros da página
    query += ' ORDER BY a.created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    logs = db.execute(query, params).fetchall()
    db.close()
    
    total_pages = (count + per_page - 1) // per_page
    
    return render_template('auditoria.html', user=u, logs=logs, page=page, total_pages=total_pages,
                         entity_type=entity_type, action=action, count=count)

@app.route('/auditoria/detalhe/<int:log_id>')
@login_required
@role_required('adm_biocognitiva','administrador')
def auditoria_detalhe(log_id):
    u=get_user(); db=get_db()
    log = db.execute('SELECT a.*, u.name as user_name FROM audit_log a JOIN users u ON a.user_id=u.id WHERE a.id=?', (log_id,)).fetchone()
    db.close()
    
    if not log:
        flash('Log não encontrado.','error')
        return redirect(url_for('auditoria'))
    
    # Parse JSON
    try:
        old_values = json.loads(log['old_values']) if log['old_values'] else {}
        new_values = json.loads(log['new_values']) if log['new_values'] else {}
    except:
        old_values = {}
        new_values = {}
    
    return render_template('auditoria_detalhe.html', user=u, log=log, old_values=old_values, new_values=new_values)

# === AGENDAMENTOS ===
@app.route('/agendamentos')
@login_required
def agendamentos():
    u=get_user(); db=get_db()
    agends=db.execute('SELECT a.*,c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id ORDER BY a.data_coleta DESC').fetchall()
    colabs=db.execute('SELECT id,name FROM colaboradores WHERE status="ativo"').fetchall(); db.close()
    return render_template('agendamentos.html', user=u, agendamentos=agends, colaboradores=colabs)

@app.route('/agendamento/novo', methods=['POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def agendamento_novo():
    u=get_user()
    motivo=request.form.get('motivo','')
    if motivo not in MOTIVOS_AGENDAMENTO_VALIDOS:
        flash('Motivo de agendamento inválido.','error')
        return redirect(url_for('agendamentos'))
    raw=request.form.getlist('exames')
    exames=sorted({e for e in raw if e in TIPOS_EXAME_VALIDOS}, key=lambda x: _EXAME_ORDER.get(x, 99))
    if len(exames)<2:
        flash('Selecione no mínimo dois exames por agendamento (PPSP).','error')
        return redirect(url_for('agendamentos'))
    db=get_db()
    db.execute(
        '''INSERT INTO agendamentos (colaborador_id,motivo,data_coleta,horario_coleta,local_coleta,exames,agendado_por)
        VALUES (?,?,?,?,?,?,?)''',
        (request.form['colaborador_id'],motivo,request.form['data_coleta'],
         request.form['horario_coleta'],request.form['local_coleta'],json.dumps(exames),u['id']),
    )
    db.commit(); db.close(); flash('Agendamento criado!','success')
    return redirect(url_for('agendamentos'))

@app.route('/agendamento/<int:id>/editar', methods=['GET','POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def agendamento_editar(id):
    u=get_user(); db=get_db()
    agend=db.execute('SELECT * FROM agendamentos WHERE id=?',(id,)).fetchone()
    if not agend: db.close(); flash('Agendamento não encontrado.','error'); return redirect(url_for('agendamentos'))
    
    if request.method=='POST':
        raw=request.form.getlist('exames')
        exames=sorted({e for e in raw if e in TIPOS_EXAME_VALIDOS}, key=lambda x: _EXAME_ORDER.get(x, 99))
        db.execute('''UPDATE agendamentos SET colaborador_id=?, motivo=?, data_coleta=?, horario_coleta=?, local_coleta=?, exames=?, status=?
            WHERE id=?''',
            (request.form['colaborador_id'], request.form['motivo'], request.form['data_coleta'],
             request.form['horario_coleta'], request.form['local_coleta'], json.dumps(exames), request.form.get('status','agendado'), id))
        db.commit(); db.close(); flash('Agendamento atualizado!','success')
        return redirect(url_for('agendamentos'))
    
    colabs=db.execute('SELECT id,name FROM colaboradores WHERE status="ativo"').fetchall()
    db.close()
    # We can reuse agendamentos.html or a separate form. Let's use a separate form for clarity.
    return render_template('agendamento_form.html', user=u, agend=agend, colaboradores=colabs)

@app.route('/agendamento/<int:id>/excluir')
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def agendamento_excluir(id):
    db=get_db()
    try:
        _delete_agendamento_dependencies(db, id)
        db.execute('DELETE FROM agendamentos WHERE id=?',(id,))
        db.commit()
        flash('Agendamento excluído.','success')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao excluir agendamento: {e}','error')
    finally:
        db.close()
    return redirect(url_for('agendamentos'))

@app.route('/agendamento/<int:id>/duplicar')
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def agendamento_duplicar(id):
    db=get_db()
    a=db.execute('SELECT * FROM agendamentos WHERE id=?',(id,)).fetchone()
    if a:
        db.execute('''INSERT INTO agendamentos (colaborador_id,motivo,data_coleta,horario_coleta,local_coleta,exames,agendado_por)
            VALUES (?,?,?,?,?,?,?)''',
            (a['colaborador_id'], a['motivo'], a['data_coleta'], a['horario_coleta'], a['local_coleta'], a['exames'], get_user()['id']))
        db.commit()
        flash('Agendamento duplicado!','success')
    db.close()
    return redirect(url_for('agendamentos'))

# === TREINAMENTOS ===
@app.route('/treinamentos')
@login_required
def treinamentos():
    u=get_user(); db=get_db()
    treins=db.execute('SELECT t.*,c.name as colab_name FROM treinamentos t LEFT JOIN colaboradores c ON t.colaborador_id=c.id ORDER BY t.data_treinamento DESC').fetchall()
    colabs=db.execute('SELECT id,name FROM colaboradores WHERE status="ativo"').fetchall(); db.close()
    return render_template('treinamentos.html', user=u, treinamentos=treins, colaboradores=colabs)

@app.route('/treinamento/novo', methods=['POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def treinamento_novo():
    u=get_user()
    arq=''
    if 'arquivo_gravacao' in request.files and request.files['arquivo_gravacao'].filename:
        f=request.files['arquivo_gravacao']
        if allowed_file(f):
            arq,_,_=save_upload(f,'documents')
        else:
            flash('Formato de arquivo não permitido.','error')
            return redirect(url_for('treinamentos'))
    _cid=(request.form.get('colaborador_id') or '').strip()
    colab_id=int(_cid) if _cid.isdigit() else None
    db=get_db()
    db.execute(
        '''INSERT INTO treinamentos (colaborador_id,titulo,motivo,tipo,data_treinamento,horario,arquivo_gravacao,agendado_por)
        VALUES (?,?,?,?,?,?,?,?)''',
        (colab_id,request.form['titulo'],request.form['motivo'],
         request.form.get('tipo','in_company'),request.form.get('data_treinamento',''),
         request.form.get('horario',''),arq,u['id']),
    )
    db.commit(); db.close(); flash('Treinamento agendado!','success')
    return redirect(url_for('treinamentos'))

# === RESULTADOS ===
@app.route('/resultados')
@login_required
def resultados():
    u=get_user(); db=get_db()
    search=request.args.get('search','')
    q=('SELECT r.*,c.name as colab_name, a.data_coleta AS agendamento_data_coleta '
       'FROM resultados_exames r JOIN colaboradores c ON r.colaborador_id=c.id '
       'LEFT JOIN agendamentos a ON r.agendamento_id=a.id')
    if search: q+=f" WHERE c.name LIKE '%{search}%' OR c.cpf LIKE '%{search}%'"
    q+=' ORDER BY r.created_at DESC'
    res=db.execute(q).fetchall()
    colabs=db.execute('SELECT id,name FROM colaboradores').fetchall(); db.close()
    return render_template('resultados.html', user=u, resultados=res, colaboradores=colabs, search=search)

@app.route('/resultado/novo', methods=['POST'])
@login_required
@role_required('tecnico','tecnico_biocognitiva','adm_biocognitiva','administrador')
def resultado_novo():
    u=get_user(); db=get_db()
    foto_doador=foto_baf=foto_termo=foto_doc=arq_res=''
    for field,sub in [('foto_doador','documents'),('foto_bafometro','documents'),('foto_termo','documents'),('foto_documento','documents'),('arquivo_resultado','documents')]:
        if field in request.files and request.files[field].filename:
            s,_,_=save_upload(request.files[field],sub)
            if field=='foto_doador': foto_doador=s
            elif field=='foto_bafometro': foto_baf=s
            elif field=='foto_termo': foto_termo=s
            elif field=='foto_documento': foto_doc=s
            elif field=='arquivo_resultado': arq_res=s
    data_coleta=(request.form.get('data_coleta') or '').strip()
    if not data_coleta:
        db.close(); flash('Data da coleta é obrigatória.','error')
        return redirect(url_for('resultados'))
    db.execute(
        '''INSERT INTO resultados_exames (colaborador_id,agendamento_id,data_coleta,resultado,observacao,foto_doador,foto_bafometro,foto_termo_consentimento,foto_documento,arquivo_resultado,lancado_por)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (request.form['colaborador_id'],request.form.get('agendamento_id') or None,data_coleta,
         request.form.get('resultado','pendente'),request.form.get('observacao',''),
         foto_doador,foto_baf,foto_termo,foto_doc,arq_res,u['id']),
    )
    db.commit(); db.close(); flash('Resultado lançado!','success')
    return redirect(url_for('resultados'))

# === RELATORIOS ===
@app.route('/relatorios')
@login_required
def relatorios():
    u=get_user(); db=get_db()
    rels=db.execute('SELECT * FROM relatorios ORDER BY created_at DESC').fetchall(); db.close()
    return render_template('relatorios.html', user=u, relatorios=rels)

@app.route('/relatorio/upload', methods=['POST'])
@login_required
@role_required('adm_biocognitiva','administrador')
def relatorio_upload():
    u=get_user()
    if 'file' not in request.files or not request.files['file'].filename:
        flash('Selecione um arquivo.','error'); return redirect(url_for('relatorios'))
    s,orig,sz=save_upload(request.files['file'],'documents')
    db=get_db()
    db.execute('INSERT INTO relatorios (titulo,descricao,filename,original_filename,file_size,uploaded_by) VALUES (?,?,?,?,?,?)',
        (request.form.get('titulo',orig),request.form.get('descricao',''),s,orig,sz,u['id']))
    db.commit(); db.close(); flash('Relatório enviado!','success')
    return redirect(url_for('relatorios'))

# === SERVICOS ===
@app.route('/servicos')
@login_required
def servicos():
    u=get_user(); db=get_db()
    servs=db.execute('SELECT s.*,u.name as solicitante FROM servicos s JOIN users u ON s.solicitado_por=u.id ORDER BY s.created_at DESC').fetchall(); db.close()
    return render_template('servicos.html', user=u, servicos=servs)

@app.route('/servico/novo', methods=['POST'])
@login_required
def servico_novo():
    u=get_user(); doc=''
    if 'documento' in request.files and request.files['documento'].filename:
        doc,_,_=save_upload(request.files['documento'],'documents')
    db=get_db()
    db.execute('INSERT INTO servicos (tipo,titulo,descricao,documento_anexo,solicitado_por) VALUES (?,?,?,?,?)',
        (request.form['tipo'],request.form['titulo'],request.form.get('descricao',''),doc,u['id']))
    db.commit(); db.close(); flash('Serviço solicitado!','success')
    return redirect(url_for('servicos'))

# === AVALIACOES (Colaborador) ===
@app.route('/avaliacao/<int:av_id>')
@login_required
def avaliacao(av_id):
    u=get_user(); db=get_db()
    av=db.execute('SELECT * FROM avaliacoes WHERE id=?',(av_id,)).fetchone()
    qs=db.execute('SELECT * FROM avaliacao_questoes WHERE avaliacao_id=? ORDER BY ordem',(av_id,)).fetchall()
    parsed=[dict(q) for q in qs]
    for p in parsed: p['opcoes']=json.loads(p['opcoes']) if p['opcoes'] else []
    colab=db.execute('SELECT * FROM colaboradores WHERE email=?',(u['email'],)).fetchone()
    tents=[]; can=True
    if colab:
        tents=db.execute('SELECT * FROM avaliacao_tentativas WHERE avaliacao_id=? AND colaborador_id=? ORDER BY tentativa_num',(av_id,colab['id'])).fetchall()
        can=len(tents)<av['max_tentativas']
        if tents and tents[-1]['aprovado']: can=False
    db.close()
    return render_template('avaliacao.html', user=u, avaliacao=av, questoes=parsed, tentativas=tents, can_attempt=can, colab=colab)

@app.route('/avaliacao/<int:av_id>/submit', methods=['POST'])
@login_required
def avaliacao_submit(av_id):
    u=get_user(); db=get_db()
    av=db.execute('SELECT * FROM avaliacoes WHERE id=?',(av_id,)).fetchone()
    qs=db.execute('SELECT * FROM avaliacao_questoes WHERE avaliacao_id=?',(av_id,)).fetchall()
    colab=db.execute('SELECT * FROM colaboradores WHERE email=?',(u['email'],)).fetchone()
    if not colab:
        db.close(); flash('Cadastro de colaborador não encontrado.','error'); return redirect(url_for('dashboard'))
    cnt=db.execute('SELECT COUNT(*) as c FROM avaliacao_tentativas WHERE avaliacao_id=? AND colaborador_id=?',(av_id,colab['id'])).fetchone()['c']
    if cnt>=av['max_tentativas']:
        db.close(); flash('Tentativas esgotadas.','error'); return redirect(url_for('avaliacao',av_id=av_id))
    total=sum(q['pontos'] for q in qs); earned=0; resps={}
    for q in qs:
        ans=request.form.get(f'q_{q["id"]}',''); resps[str(q['id'])]=ans
        if ans==q['resposta_correta']: earned+=q['pontos']
    nota=round((earned/total*av['nota_maxima']) if total>0 else 0, 2)
    aprovado=1 if nota>=av['nota_minima'] else 0
    db.execute('''INSERT INTO avaliacao_tentativas (avaliacao_id,colaborador_id,respostas,nota,nota_maxima,aprovado,tentativa_num)
        VALUES (?,?,?,?,?,?,?)''',(av_id,colab['id'],json.dumps(resps),nota,av['nota_maxima'],aprovado,cnt+1))
    db.commit(); db.close()
    msg=f'Nota: {nota}/{av["nota_maxima"]}. '
    if aprovado: msg+='Aprovado!'
    elif cnt+1<av['max_tentativas']: msg+=f'Reprovado. Você tem mais {av["max_tentativas"]-cnt-1} tentativa(s).'
    else: msg+='Reprovado. Tentativas esgotadas.'
    flash(msg,'success' if aprovado else 'warning')
    return redirect(url_for('avaliacao',av_id=av_id))

# === VIDEO AULAS ===
@app.route('/video-aulas')
@login_required
def video_aulas():
    u=get_user(); db=get_db()
    videos=db.execute('SELECT * FROM video_aulas ORDER BY ordem').fetchall(); db.close()
    return render_template('video_aulas.html', user=u, videos=videos)

# === SORTEIO ===
@app.route('/sorteio', methods=['GET','POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def sorteio():
    u=get_user(); db=get_db()
    if request.method=='POST':
        qtd=int(request.form.get('quantidade',1))
        colabs=db.execute('SELECT id,name,cpf FROM colaboradores WHERE status="ativo"').fetchall()
        lst=[dict(c) for c in colabs]
        sel=random.sample(lst,min(qtd,len(lst))) if lst else []
        db.execute('INSERT INTO sorteios (titulo,quantidade,colaboradores_sorteados,realizado_por) VALUES (?,?,?,?)',
            (request.form.get('titulo','Sorteio Aleatório'),qtd,json.dumps(sel),u['id']))
        db.commit()
        names=', '.join(s['name'] for s in sel)
        flash(f'Sorteados: {names}','success')
    sorts=db.execute('SELECT * FROM sorteios ORDER BY created_at DESC').fetchall(); db.close()
    return render_template('sorteio.html', user=u, sorteios=sorts)

# === INSTITUCIONAL ===
@app.route('/institucional')
@login_required
def institucional():
    u=get_user(); db=get_db()
    docs=db.execute('SELECT * FROM institutional_docs ORDER BY created_at DESC').fetchall(); db.close()
    return render_template('institucional.html', user=u, docs=docs)

@app.route('/institucional/upload', methods=['POST'])
@login_required
@role_required('adm_biocognitiva','administrador')
def institucional_upload():
    u=get_user()
    if 'file' not in request.files or not request.files['file'].filename:
        flash('Selecione um arquivo.','error'); return redirect(url_for('institucional'))
    s,orig,sz=save_upload(request.files['file'],'documents')
    db=get_db()
    db.execute('INSERT INTO institutional_docs (category,title,description,filename,original_filename,file_size,uploaded_by) VALUES (?,?,?,?,?,?,?)',
        (request.form.get('category','institucional'),request.form.get('title',orig),request.form.get('description',''),s,orig,sz,u['id']))
    db.commit(); db.close(); flash('Documento enviado!','success')
    return redirect(url_for('institucional'))

# === FINANCEIRO ===
@app.route('/financeiro')
@login_required
@role_required('adm_biocognitiva','administrador')
def financeiro():
    u=get_user(); db=get_db()
    docs=db.execute('SELECT * FROM financeiro ORDER BY created_at DESC').fetchall(); db.close()
    return render_template('financeiro.html', user=u, docs=docs)

@app.route('/financeiro/upload', methods=['POST'])
@login_required
@role_required('adm_biocognitiva','administrador')
def financeiro_upload():
    u=get_user()
    if 'file' not in request.files or not request.files['file'].filename:
        flash('Selecione um arquivo.','error'); return redirect(url_for('financeiro'))
    s,orig,sz=save_upload(request.files['file'],'documents')
    db=get_db()
    db.execute('INSERT INTO financeiro (tipo,titulo,descricao,filename,original_filename,file_size,uploaded_by) VALUES (?,?,?,?,?,?,?)',
        (request.form.get('tipo','boleto'),request.form.get('titulo',orig),request.form.get('descricao',''),s,orig,sz,u['id']))
    db.commit(); db.close(); flash('Documento financeiro enviado!','success')
    return redirect(url_for('financeiro'))

# === FALTAS (Técnico) ===
@app.route('/faltas')
@login_required
@role_required('tecnico','adm_biocognitiva','administrador')
def faltas():
    u=get_user(); db=get_db()
    fs=db.execute('SELECT f.*,c.name as colab_name FROM faltas f JOIN colaboradores c ON f.colaborador_id=c.id ORDER BY f.data_falta DESC').fetchall()
    colabs=db.execute('SELECT id,name FROM colaboradores').fetchall(); db.close()
    return render_template('faltas.html', user=u, faltas=fs, colaboradores=colabs)

@app.route('/falta/nova', methods=['POST'])
@login_required
@role_required('tecnico','adm_biocognitiva','administrador')
def falta_nova():
    u=get_user(); db=get_db()
    db.execute('INSERT INTO faltas (colaborador_id,data_falta,observacao,registrado_por) VALUES (?,?,?,?)',
        (request.form['colaborador_id'],request.form['data_falta'],request.form.get('observacao',''),u['id']))
    # Update agendamento status if exists
    db.execute("UPDATE agendamentos SET status='falta' WHERE colaborador_id=? AND data_coleta=?",
        (request.form['colaborador_id'],request.form['data_falta']))
    db.commit(); db.close(); flash('Falta registrada!','success')
    return redirect(url_for('faltas'))

# === CONTROLE POSITIVO (Técnico) ===
@app.route('/controle-positivo')
@login_required
@role_required('tecnico','adm_biocognitiva','administrador')
def controle_positivo():
    u=get_user(); db=get_db()
    cps=db.execute('SELECT cp.*,c.name as colab_name FROM controle_positivo cp JOIN colaboradores c ON cp.colaborador_id=c.id ORDER BY cp.created_at DESC').fetchall()
    colabs=db.execute('SELECT id,name FROM colaboradores').fetchall(); db.close()
    return render_template('controle_positivo.html', user=u, controles=cps, colaboradores=colabs)

@app.route('/controle-positivo/novo', methods=['POST'])
@login_required
@role_required('tecnico','adm_biocognitiva','administrador')
def controle_positivo_novo():
    u=get_user()
    tipo=request.form.get('tipo_evento','positivo_amostra')
    if tipo not in TIPO_EVENTO_LABELS:
        tipo='positivo_amostra'
    arq=''
    if 'arquivo' in request.files and request.files['arquivo'].filename:
        arq,_,_=save_upload(request.files['arquivo'],'documents')
    da=(request.form.get('data_agendamento') or '').strip()
    ha=(request.form.get('horario_agendamento') or '').strip()
    db=get_db()
    db.execute(
        '''INSERT INTO controle_positivo (colaborador_id,tipo_evento,data_agendamento,horario_agendamento,info_amostra,remessa_correio,arquivo_resultado,observacao,registrado_por)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (request.form['colaborador_id'],tipo,da,ha,
         request.form.get('info_amostra',''),request.form.get('remessa_correio',''),arq,request.form.get('observacao',''),u['id']),
    )
    db.commit(); db.close(); flash('Evento impeditivo registrado!','success')
    return redirect(url_for('controle_positivo'))


# --- Ações por linha (editar / duplicar / excluir) — mesmo padrão de colaboradores/agendamentos ---

@app.route('/treinamento/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def treinamento_editar(id):
    u = get_user()
    db = get_db()
    t = db.execute('SELECT * FROM treinamentos WHERE id=?', (id,)).fetchone()
    if not t:
        db.close()
        flash('Treinamento não encontrado.', 'error')
        return redirect(url_for('treinamentos'))
    if request.method == 'POST':
        _cid = (request.form.get('colaborador_id') or '').strip()
        colab_id = int(_cid) if _cid.isdigit() else None
        arq = t['arquivo_gravacao']
        if 'arquivo_gravacao' in request.files and request.files['arquivo_gravacao'].filename:
            f = request.files['arquivo_gravacao']
            if allowed_file(f):
                _unlink_upload_doc(arq or '')
                arq, _, _ = save_upload(f, 'documents')
            else:
                db.close()
                flash('Formato de arquivo não permitido.', 'error')
                return redirect(url_for('treinamento_editar', id=id))
        db.execute(
            '''UPDATE treinamentos SET colaborador_id=?, titulo=?, motivo=?, tipo=?, data_treinamento=?, horario=?, arquivo_gravacao=?, status=?
            WHERE id=?''',
            (
                colab_id,
                request.form['titulo'],
                request.form['motivo'],
                request.form.get('tipo', 'in_company'),
                request.form.get('data_treinamento', ''),
                request.form.get('horario', ''),
                arq,
                request.form.get('status', 'agendado'),
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Treinamento atualizado!', 'success')
        return redirect(url_for('treinamentos'))
    colabs = db.execute('SELECT id,name FROM colaboradores WHERE status="ativo"').fetchall()
    db.close()
    return render_template('treinamento_form.html', user=u, treinamento=t, colaboradores=colabs)


@app.route('/treinamento/<int:id>/duplicar')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def treinamento_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'treinamento', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Treinamento duplicado!', 'success')
    return redirect(url_for('treinamentos'))


@app.route('/treinamento/<int:id>/excluir')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def treinamento_excluir(id):
    db = get_db()
    try:
        row = db.execute('SELECT arquivo_gravacao FROM treinamentos WHERE id=?', (id,)).fetchone()
        if row and row['arquivo_gravacao']:
            _unlink_upload_doc(row['arquivo_gravacao'])
        db.execute('DELETE FROM treinamentos WHERE id=?', (id,))
        db.commit()
        flash('Treinamento excluído.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao excluir treinamento: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('treinamentos'))


@app.route('/resultado/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def resultado_editar(id):
    u = get_user()
    db = get_db()
    r = db.execute('SELECT * FROM resultados_exames WHERE id=?', (id,)).fetchone()
    if not r:
        db.close()
        flash('Resultado não encontrado.', 'error')
        return redirect(url_for('resultados'))
    if request.method == 'POST':
        foto_doador = r['foto_doador']
        foto_baf = r['foto_bafometro']
        foto_termo = r['foto_termo_consentimento']
        foto_doc = r['foto_documento']
        arq_res = r['arquivo_resultado']
        if request.files.get('foto_doador') and request.files['foto_doador'].filename:
            _unlink_upload_doc(foto_doador or '')
            foto_doador, _, _ = save_upload(request.files['foto_doador'], 'documents')
        if request.files.get('foto_bafometro') and request.files['foto_bafometro'].filename:
            _unlink_upload_doc(foto_baf or '')
            foto_baf, _, _ = save_upload(request.files['foto_bafometro'], 'documents')
        if request.files.get('foto_termo') and request.files['foto_termo'].filename:
            _unlink_upload_doc(foto_termo or '')
            foto_termo, _, _ = save_upload(request.files['foto_termo'], 'documents')
        if request.files.get('foto_documento') and request.files['foto_documento'].filename:
            _unlink_upload_doc(foto_doc or '')
            foto_doc, _, _ = save_upload(request.files['foto_documento'], 'documents')
        if request.files.get('arquivo_resultado') and request.files['arquivo_resultado'].filename:
            _unlink_upload_doc(arq_res or '')
            arq_res, _, _ = save_upload(request.files['arquivo_resultado'], 'documents')
        data_coleta = (request.form.get('data_coleta') or '').strip()
        if not data_coleta:
            db.close()
            flash('Data da coleta é obrigatória.', 'error')
            return redirect(url_for('resultado_editar', id=id))
        db.execute(
            '''UPDATE resultados_exames SET colaborador_id=?, data_coleta=?, resultado=?, observacao=?,
            foto_doador=?, foto_bafometro=?, foto_termo_consentimento=?, foto_documento=?, arquivo_resultado=? WHERE id=?''',
            (
                request.form['colaborador_id'],
                data_coleta,
                request.form.get('resultado', 'pendente'),
                request.form.get('observacao', ''),
                foto_doador,
                foto_baf,
                foto_termo,
                foto_doc,
                arq_res,
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Resultado atualizado!', 'success')
        return redirect(url_for('resultados'))
    colabs = db.execute('SELECT id,name FROM colaboradores').fetchall()
    db.close()
    return render_template('resultado_form.html', user=u, resultado=r, colaboradores=colabs)


@app.route('/resultado/<int:id>/duplicar')
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def resultado_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'resultado', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Resultado duplicado!', 'success')
    return redirect(url_for('resultados'))


@app.route('/resultado/<int:id>/excluir')
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def resultado_excluir(id):
    db = get_db()
    try:
        r = db.execute(
            'SELECT foto_doador,foto_bafometro,foto_termo_consentimento,foto_documento,arquivo_resultado FROM resultados_exames WHERE id=?',
            (id,),
        ).fetchone()
        if r:
            for fn in (
                r['foto_doador'],
                r['foto_bafometro'],
                r['foto_termo_consentimento'],
                r['foto_documento'],
                r['arquivo_resultado'],
            ):
                _unlink_upload_doc(fn or '')
            
            # Cleanup references
            db.execute('UPDATE controle_positivo SET resultado_id=NULL WHERE resultado_id=?', (id,))
            db.execute('UPDATE rastreabilidade SET resultado_id=NULL WHERE resultado_id=?', (id,))
            
            db.execute('DELETE FROM resultados_exames WHERE id=?', (id,))
            db.commit()
            flash('Resultado excluído.', 'success')
        else:
            flash('Resultado não encontrado.', 'error')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao excluir resultado: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('resultados'))


@app.route('/relatorio/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('adm_biocognitiva', 'administrador')
def relatorio_editar(id):
    u = get_user()
    db = get_db()
    r = db.execute('SELECT * FROM relatorios WHERE id=?', (id,)).fetchone()
    if not r:
        db.close()
        flash('Relatório não encontrado.', 'error')
        return redirect(url_for('relatorios'))
    if request.method == 'POST':
        db.execute(
            'UPDATE relatorios SET titulo=?, descricao=?, categoria=? WHERE id=?',
            (
                request.form.get('titulo', r['titulo']),
                request.form.get('descricao', ''),
                request.form.get('categoria', r.get('categoria') or 'geral'),
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Relatório atualizado!', 'success')
        return redirect(url_for('relatorios'))
    db.close()
    return render_template('relatorio_form.html', user=u, relatorio=r)


@app.route('/relatorio/<int:id>/duplicar')
@login_required
@role_required('adm_biocognitiva', 'administrador')
def relatorio_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'relatorio', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Relatório duplicado!', 'success')
    return redirect(url_for('relatorios'))


@app.route('/relatorio/<int:id>/excluir')
@login_required
@role_required('adm_biocognitiva', 'administrador')
def relatorio_excluir(id):
    db = get_db()
    row = db.execute('SELECT filename FROM relatorios WHERE id=?', (id,)).fetchone()
    if row and row['filename']:
        _unlink_upload_doc(row['filename'])
    db.execute('DELETE FROM relatorios WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Relatório excluído.', 'success')
    return redirect(url_for('relatorios'))


@app.route('/servico/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def servico_editar(id):
    u = get_user()
    db = get_db()
    s = db.execute('SELECT * FROM servicos WHERE id=?', (id,)).fetchone()
    if not s:
        db.close()
        flash('Solicitação não encontrada.', 'error')
        return redirect(url_for('servicos'))
    if request.method == 'POST':
        doc = s['documento_anexo']
        if 'documento' in request.files and request.files['documento'].filename:
            _unlink_upload_doc(doc)
            doc, _, _ = save_upload(request.files['documento'], 'documents')
        db.execute(
            'UPDATE servicos SET tipo=?, titulo=?, descricao=?, documento_anexo=?, status=? WHERE id=?',
            (
                request.form['tipo'],
                request.form['titulo'],
                request.form.get('descricao', ''),
                doc,
                request.form.get('status', 'pendente'),
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Solicitação atualizada!', 'success')
        return redirect(url_for('servicos'))
    db.close()
    return render_template('servico_form.html', user=u, servico=s)


@app.route('/servico/<int:id>/duplicar')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def servico_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'servico', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Solicitação duplicada!', 'success')
    return redirect(url_for('servicos'))


@app.route('/servico/<int:id>/excluir')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def servico_excluir(id):
    db = get_db()
    s = db.execute('SELECT documento_anexo,documento_resposta FROM servicos WHERE id=?', (id,)).fetchone()
    if s:
        _unlink_upload_doc(s['documento_anexo'])
        _unlink_upload_doc(s['documento_resposta'] or '')
    db.execute('DELETE FROM servicos WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Solicitação excluída.', 'success')
    return redirect(url_for('servicos'))


@app.route('/sorteio/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def sorteio_editar(id):
    u = get_user()
    db = get_db()
    s = db.execute('SELECT * FROM sorteios WHERE id=?', (id,)).fetchone()
    if not s:
        db.close()
        flash('Sorteio não encontrado.', 'error')
        return redirect(url_for('sorteio'))
    if request.method == 'POST':
        db.execute(
            'UPDATE sorteios SET titulo=?, quantidade=? WHERE id=?',
            (request.form.get('titulo', s['titulo']), int(request.form.get('quantidade', s['quantidade'] or 1)), id),
        )
        db.commit()
        db.close()
        flash('Sorteio atualizado!', 'success')
        return redirect(url_for('sorteio'))
    db.close()
    return render_template('sorteio_form.html', user=u, sorteio=s)


@app.route('/sorteio/<int:id>/duplicar')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def sorteio_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'sorteio', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Sorteio duplicado!', 'success')
    return redirect(url_for('sorteio'))


@app.route('/sorteio/<int:id>/excluir')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def sorteio_excluir(id):
    db = get_db()
    db.execute('DELETE FROM sorteios WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Sorteio excluído.', 'success')
    return redirect(url_for('sorteio'))


@app.route('/falta/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def falta_editar(id):
    u = get_user()
    db = get_db()
    f = db.execute('SELECT * FROM faltas WHERE id=?', (id,)).fetchone()
    if not f:
        db.close()
        flash('Falta não encontrada.', 'error')
        return redirect(url_for('faltas'))
    if request.method == 'POST':
        db.execute(
            'UPDATE faltas SET colaborador_id=?, data_falta=?, observacao=? WHERE id=?',
            (request.form['colaborador_id'], request.form['data_falta'], request.form.get('observacao', ''), id),
        )
        db.execute(
            "UPDATE agendamentos SET status='falta' WHERE colaborador_id=? AND data_coleta=?",
            (request.form['colaborador_id'], request.form['data_falta']),
        )
        db.commit()
        db.close()
        flash('Falta atualizada!', 'success')
        return redirect(url_for('faltas'))
    colabs = db.execute('SELECT id,name FROM colaboradores').fetchall()
    db.close()
    return render_template('falta_form.html', user=u, falta=f, colaboradores=colabs)


@app.route('/falta/<int:id>/duplicar')
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def falta_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'falta', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Falta duplicada!', 'success')
    return redirect(url_for('faltas'))


@app.route('/falta/<int:id>/excluir')
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def falta_excluir(id):
    db = get_db()
    db.execute('DELETE FROM faltas WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Falta excluída.', 'success')
    return redirect(url_for('faltas'))


@app.route('/controle-positivo/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def controle_positivo_editar(id):
    u = get_user()
    db = get_db()
    cp = db.execute('SELECT * FROM controle_positivo WHERE id=?', (id,)).fetchone()
    if not cp:
        db.close()
        flash('Registro não encontrado.', 'error')
        return redirect(url_for('controle_positivo'))
    if request.method == 'POST':
        tipo = request.form.get('tipo_evento', 'positivo_amostra')
        if tipo not in TIPO_EVENTO_LABELS:
            tipo = 'positivo_amostra'
        arq = cp['arquivo_resultado']
        if 'arquivo' in request.files and request.files['arquivo'].filename:
            _unlink_upload_doc(arq)
            arq, _, _ = save_upload(request.files['arquivo'], 'documents')
        da = (request.form.get('data_agendamento') or '').strip()
        ha = (request.form.get('horario_agendamento') or '').strip()
        db.execute(
            '''UPDATE controle_positivo SET colaborador_id=?, tipo_evento=?, data_agendamento=?, horario_agendamento=?,
            info_amostra=?, remessa_correio=?, arquivo_resultado=?, observacao=? WHERE id=?''',
            (
                request.form['colaborador_id'],
                tipo,
                da,
                ha,
                request.form.get('info_amostra', ''),
                request.form.get('remessa_correio', ''),
                arq,
                request.form.get('observacao', ''),
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Evento atualizado!', 'success')
        return redirect(url_for('controle_positivo'))
    colabs = db.execute('SELECT id,name FROM colaboradores').fetchall()
    db.close()
    return render_template('evento_impeditivo_form.html', user=u, evento=cp, colaboradores=colabs)


@app.route('/controle-positivo/<int:id>/duplicar')
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def controle_positivo_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'controle_positivo', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Registro duplicado!', 'success')
    return redirect(url_for('controle_positivo'))


@app.route('/controle-positivo/<int:id>/excluir')
@login_required
@role_required('tecnico', 'tecnico_biocognitiva', 'adm_biocognitiva', 'administrador')
def controle_positivo_excluir(id):
    db = get_db()
    cp = db.execute('SELECT arquivo_resultado FROM controle_positivo WHERE id=?', (id,)).fetchone()
    if cp and cp['arquivo_resultado']:
        _unlink_upload_doc(cp['arquivo_resultado'])
    db.execute('DELETE FROM controle_positivo WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Registro excluído.', 'success')
    return redirect(url_for('controle_positivo'))


@app.route('/cliente/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('adm_biocognitiva', 'administrador')
def cliente_editar(id):
    u = get_user()
    db = get_db()
    c = db.execute('SELECT * FROM clientes_empresa WHERE id=?', (id,)).fetchone()
    if not c:
        db.close()
        flash('Cliente não encontrado.', 'error')
        return redirect(url_for('clientes'))
    if request.method == 'POST':
        rs = request.form.get('razao_social', '').strip()
        if not rs:
            db.close()
            flash('Razão social é obrigatória.', 'error')
            return redirect(url_for('cliente_editar', id=id))
        db.execute(
            '''UPDATE clientes_empresa SET razao_social=?, nome_fantasia=?, cnpj=?, cidade=?, contato_nome=?, telefone=?, email=?, observacao=?
            WHERE id=?''',
            (
                rs,
                request.form.get('nome_fantasia', '').strip(),
                request.form.get('cnpj', '').strip(),
                request.form.get('cidade', '').strip(),
                request.form.get('contato_nome', '').strip(),
                request.form.get('telefone', '').strip(),
                request.form.get('email', '').strip(),
                request.form.get('observacao', '').strip(),
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Cliente atualizado!', 'success')
        return redirect(url_for('clientes'))
    db.close()
    return render_template('cliente_form.html', user=u, cliente=c)


@app.route('/cliente/<int:id>/duplicar')
@login_required
@role_required('adm_biocognitiva', 'administrador')
def cliente_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'cliente', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Cliente duplicado!', 'success')
    return redirect(url_for('clientes'))


@app.route('/cliente/<int:id>/excluir')
@login_required
@role_required('adm_biocognitiva', 'administrador')
def cliente_excluir(id):
    db = get_db()
    db.execute('DELETE FROM clientes_empresa WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Cliente excluído.', 'success')
    return redirect(url_for('clientes'))


@app.route('/subcontratada/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def subcontratada_editar(id):
    u = get_user()
    db = get_db()
    s = db.execute('SELECT * FROM subcontratadas WHERE id=?', (id,)).fetchone()
    if not s:
        db.close()
        flash('Subcontratada não encontrada.', 'error')
        return redirect(url_for('subcontratadas'))
    if request.method == 'POST':
        nf = request.form.get('nome_fantasia', '').strip()
        if not nf:
            db.close()
            flash('Nome fantasia é obrigatório.', 'error')
            return redirect(url_for('subcontratada_editar', id=id))
        db.execute(
            '''UPDATE subcontratadas SET nome_fantasia=?, razao_social=?, cnpj=?, contato_nome=?, telefone=?, email=?, observacao=?
            WHERE id=?''',
            (
                nf,
                request.form.get('razao_social', '').strip(),
                request.form.get('cnpj', '').strip(),
                request.form.get('contato_nome', '').strip(),
                request.form.get('telefone', '').strip(),
                request.form.get('email', '').strip(),
                request.form.get('observacao', '').strip(),
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Subcontratada atualizada!', 'success')
        return redirect(url_for('subcontratadas'))
    db.close()
    return render_template('subcontratada_form.html', user=u, subcontratada=s)


@app.route('/subcontratada/<int:id>/duplicar')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def subcontratada_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'subcontratada', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Subcontratada duplicada!', 'success')
    return redirect(url_for('subcontratadas'))


@app.route('/subcontratada/<int:id>/excluir')
@login_required
@role_required('supervisor', 'adm_biocognitiva', 'administrador')
def subcontratada_excluir(id):
    db = get_db()
    db.execute('DELETE FROM subcontratadas WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Subcontratada excluída.', 'success')
    return redirect(url_for('subcontratadas'))


@app.route('/financeiro/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('adm_biocognitiva', 'administrador')
def financeiro_editar(id):
    u = get_user()
    db = get_db()
    d = db.execute('SELECT * FROM financeiro WHERE id=?', (id,)).fetchone()
    if not d:
        db.close()
        flash('Documento não encontrado.', 'error')
        return redirect(url_for('financeiro'))
    if request.method == 'POST':
        fn, orig, sz = d['filename'], d['original_filename'], d['file_size']
        if 'file' in request.files and request.files['file'].filename:
            _unlink_upload_doc(fn)
            fn, orig, sz = save_upload(request.files['file'], 'documents')
        db.execute(
            'UPDATE financeiro SET tipo=?, titulo=?, descricao=?, filename=?, original_filename=?, file_size=? WHERE id=?',
            (
                request.form.get('tipo', d['tipo']),
                request.form.get('titulo', d['titulo']),
                request.form.get('descricao', ''),
                fn,
                orig,
                sz,
                id,
            ),
        )
        db.commit()
        db.close()
        flash('Documento atualizado!', 'success')
        return redirect(url_for('financeiro'))
    db.close()
    return render_template('financeiro_form.html', user=u, doc=d)


@app.route('/financeiro/<int:id>/duplicar')
@login_required
@role_required('adm_biocognitiva', 'administrador')
def financeiro_duplicar(id):
    db = get_db()
    _bulk_duplicate_entity(db, 'financeiro', id, get_user()['id'])
    db.commit()
    db.close()
    flash('Documento duplicado!', 'success')
    return redirect(url_for('financeiro'))


@app.route('/financeiro/<int:id>/excluir')
@login_required
@role_required('adm_biocognitiva', 'administrador')
def financeiro_excluir(id):
    db = get_db()
    row = db.execute('SELECT filename FROM financeiro WHERE id=?', (id,)).fetchone()
    if row and row['filename']:
        _unlink_upload_doc(row['filename'])
    db.execute('DELETE FROM financeiro WHERE id=?', (id,))
    db.commit()
    db.close()
    flash('Documento excluído.', 'success')
    return redirect(url_for('financeiro'))


@app.route('/clientes', methods=['GET','POST'])
@login_required
@role_required('adm_biocognitiva','administrador')
def clientes():
    u=get_user(); db=get_db()
    if request.method=='POST':
        rs=request.form.get('razao_social','').strip()
        if not rs:
            flash('Razão social é obrigatória.','error')
        else:
            db.execute(
                '''INSERT INTO clientes_empresa (razao_social,nome_fantasia,cnpj,cidade,contato_nome,telefone,email,observacao,registered_by)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (rs,request.form.get('nome_fantasia','').strip(),request.form.get('cnpj','').strip(),
                 request.form.get('cidade','').strip(),request.form.get('contato_nome','').strip(),
                 request.form.get('telefone','').strip(),request.form.get('email','').strip(),
                 request.form.get('observacao','').strip(),u['id']),
            )
            db.commit(); flash('Cliente cadastrado!','success')
    rows=db.execute('SELECT * FROM clientes_empresa ORDER BY razao_social').fetchall(); db.close()
    return render_template('clientes.html', user=u, clientes=rows)


@app.route('/subcontratadas', methods=['GET','POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def subcontratadas():
    u=get_user(); db=get_db()
    if request.method=='POST':
        nf=request.form.get('nome_fantasia','').strip()
        if not nf:
            flash('Nome fantasia é obrigatório.','error')
        else:
            db.execute(
                '''INSERT INTO subcontratadas (nome_fantasia,razao_social,cnpj,contato_nome,telefone,email,observacao,registered_by)
                VALUES (?,?,?,?,?,?,?,?)''',
                (nf,request.form.get('razao_social','').strip(),request.form.get('cnpj','').strip(),
                 request.form.get('contato_nome','').strip(),request.form.get('telefone','').strip(),
                 request.form.get('email','').strip(),request.form.get('observacao','').strip(),u['id']),
            )
            db.commit(); flash('Subcontratada cadastrada!','success')
    rows=db.execute('SELECT * FROM subcontratadas ORDER BY nome_fantasia').fetchall(); db.close()
    return render_template('subcontratadas.html', user=u, subcontratadas=rows)


@app.route('/estoque-kits')
@login_required
@role_required('adm_biocognitiva','administrador')
def estoque_kits():
    u=get_user()
    return render_template('estoque_kits.html', user=u)


# === ADMIN USERS ===
@app.route('/admin/users')
@login_required
@role_required('administrador')
def admin_users():
    u=get_user(); db=get_db()
    users=db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall(); db.close()
    return render_template('admin_users.html', user=u, users=users)

@app.route('/admin/user/<int:uid>/toggle', methods=['POST'])
@login_required
@role_required('administrador')
def toggle_user(uid):
    u = get_user()
    db=get_db()
    usr=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if usr:
        new_status = 0 if usr['active'] else 1
        db.execute('UPDATE users SET active=? WHERE id=?',(new_status, uid))
        db.commit()
        log_audit(u['id'], 'UPDATE', 'users', uid, 
                  old_values={'active': usr['active']}, 
                  new_values={'active': new_status},
                  changes=f"status: {'Ativo' if usr['active'] else 'Inativo'} → {'Ativo' if new_status else 'Inativo'}")
    db.close()
    return redirect(url_for('admin_users'))

@app.route('/admin/user/new', methods=['GET', 'POST'])
@login_required
@role_required('administrador')
def create_user():
    u = get_user()
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        cpf = request.form.get('cpf', '')
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        funcao = request.form.get('funcao', '')
        data_admissao = request.form.get('data_admissao', '')
        empresa = request.form.get('empresa', '')

        if not name or not email or not password or not role:
            flash('Todos os campos obrigatórios devem ser preenchidos.', 'danger')
            return redirect(url_for('create_user'))

        db = get_db()
        try:
            password_hash = generate_password_hash(password)
            cursor = db.execute('''INSERT INTO users (name, email, password_hash, role, cpf, phone, address, funcao, data_admissao, empresa)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (name, email, password_hash, role, cpf, phone, address, funcao, data_admissao, empresa))
            db.commit()
            new_id = cursor.lastrowid
            
            new_values = {
                'name': name, 'email': email, 'role': role, 'cpf': cpf, 'phone': phone,
                'address': address, 'funcao': funcao, 'data_admissao': data_admissao, 'empresa': empresa
            }
            log_audit(u['id'], 'CREATE', 'users', new_id, old_values={}, new_values=new_values)
            
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('admin_users'))
        except sqlite3.IntegrityError:
            flash('Email já cadastrado.', 'danger')
        finally:
            db.close()
    return render_template('user_form.html', user=u, action='create')

@app.route('/admin/user/<int:uid>/edit', methods=['GET', 'POST'])
@login_required
@role_required('administrador')
def edit_user(uid):
    u = get_user()
    db = get_db()
    usr = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    
    if not usr:
        db.close()
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        cpf = request.form.get('cpf', '')
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        funcao = request.form.get('funcao', '')
        data_admissao = request.form.get('data_admissao', '')
        empresa = request.form.get('empresa', '')
        active = 1 if request.form.get('active') else 0
        password = request.form.get('password')

        if not name or not email or not role:
            flash('Nome, Email e Perfil são obrigatórios.', 'danger')
            return redirect(url_for('edit_user', uid=uid))

        try:
            old_values = dict(usr)
            if password:
                password_hash = generate_password_hash(password)
                db.execute('''UPDATE users SET name=?, email=?, password_hash=?, role=?, cpf=?, phone=?, address=?, funcao=?, data_admissao=?, empresa=?, active=?, updated_at=CURRENT_TIMESTAMP
                              WHERE id=?''',
                           (name, email, password_hash, role, cpf, phone, address, funcao, data_admissao, empresa, active, uid))
            else:
                db.execute('''UPDATE users SET name=?, email=?, role=?, cpf=?, phone=?, address=?, funcao=?, data_admissao=?, empresa=?, active=?, updated_at=CURRENT_TIMESTAMP
                              WHERE id=?''',
                           (name, email, role, cpf, phone, address, funcao, data_admissao, empresa, active, uid))
            
            db.commit()
            
            new_values = {
                'name': name, 'email': email, 'role': role, 'cpf': cpf, 'phone': phone,
                'address': address, 'funcao': funcao, 'data_admissao': data_admissao, 
                'empresa': empresa, 'active': active
            }
            changes = get_field_changes(old_values, new_values)
            log_audit(u['id'], 'UPDATE', 'users', uid, old_values=old_values, new_values=new_values, changes=changes)
            
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('admin_users'))
        except sqlite3.IntegrityError:
            flash('Email já cadastrado para outro usuário.', 'danger')
        finally:
            db.close()
            
    db.close()
    return render_template('user_form.html', user=u, action='edit', target_user=usr)

@app.route('/admin/user/<int:uid>/delete', methods=['POST'])
@login_required
@role_required('administrador')
def delete_user(uid):
    u = get_user()
    if uid == u['id']:
        flash('Você não pode deletar seu próprio usuário.', 'danger')
        return redirect(url_for('admin_users'))

    db = get_db()
    usr = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if usr:
        old_values = dict(usr)
        db.execute('DELETE FROM users WHERE id = ?', (uid,))
        db.commit()
        log_audit(u['id'], 'DELETE', 'users', uid, old_values=old_values, new_values={})
    db.close()
    flash('Usuário deletado com sucesso!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete_batch', methods=['POST'])
@login_required
@role_required('administrador')
def delete_users_batch():
    u = get_user()
    user_ids = request.form.getlist('user_ids')
    if not user_ids:
        flash('Nenhum usuário selecionado.', 'danger')
        return redirect(url_for('admin_users'))

    # Impedir deletar o próprio usuário
    if str(u['id']) in user_ids:
        flash('Você não pode deletar seu próprio usuário na exclusão em massa.', 'danger')
        return redirect(url_for('admin_users'))

    db = get_db()
    for uid in user_ids:
        usr = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if usr:
            old_values = dict(usr)
            db.execute('DELETE FROM users WHERE id = ?', (uid,))
            log_audit(u['id'], 'DELETE', 'users', uid, old_values=old_values, new_values={})
    
    db.commit()
    db.close()
    flash(f'{len(user_ids)} usuário(s) deletado(s) com sucesso!', 'success')
    return redirect(url_for('admin_users'))

# === SETTINGS ===
@app.route('/settings', methods=['GET','POST'])
@login_required
@role_required('administrador')
def settings():
    u=get_user(); db=get_db()
    if request.method=='POST':
        for k in ('nota_minima','nota_maxima','max_tentativas','platform_name'):
            v=request.form.get(k)
            if v: db.execute('UPDATE settings SET value=? WHERE key=?',(v,k))
        db.commit(); flash('Configurações salvas!','success')
    s={r['key']:r['value'] for r in db.execute('SELECT * FROM settings').fetchall()}; db.close()
    return render_template('settings.html', user=u, settings=s)

with app.app_context():
    init_db()

if __name__=='__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
