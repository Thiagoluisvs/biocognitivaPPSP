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
    colab=db.execute('SELECT * FROM colaboradores WHERE id=?',(id,)).fetchone()
    if colab:
        old_values = dict(colab)
        db.execute('DELETE FROM colaboradores WHERE id=?',(id,))
        log_audit(u['id'], 'DELETE', 'colaboradores', id, old_values=old_values, new_values={})
        db.commit()
    db.close()
    flash('Colaborador excluído.','success')
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

@app.route('/bulk-action/<action>', methods=['POST'])
@login_required
@role_required('supervisor','adm_biocognitiva','administrador')
def bulk_action(action):
    ids = json.loads(request.form.get('ids', '[]'))
    if not ids: flash('Nenhum item selecionado.','warning'); return redirect(request.referrer)
    
    db = get_db()
    if action == 'excluir':
        for i in ids: db.execute('DELETE FROM colaboradores WHERE id=?', (i,))
        flash(f'{len(ids)} itens excluídos.','success')
    elif action == 'duplicar':
        for i in ids:
            c = db.execute('SELECT * FROM colaboradores WHERE id=?', (i,)).fetchone()
            if c:
                db.execute('''INSERT INTO colaboradores (name,cpf,endereco,funcao,data_admissao,telefone,email,empresa,registered_by)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (c['name'] + ' (Cópia)', c['cpf'], c['endereco'], c['funcao'], c['data_admissao'], c['telefone'], c['email'], c['empresa'], get_user()['id']))
        flash(f'{len(ids)} itens duplicados.','success')
    elif action == 'editar':
        # Placeholder for mass edit, usually opens a special form
        flash('Edição em massa selecionada para ' + str(len(ids)) + ' itens.','info')
        
    db.commit(); db.close()
    return redirect(request.referrer or url_for('colaboradores'))

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
    db.execute('DELETE FROM agendamentos WHERE id=?',(id,))
    db.commit(); db.close(); flash('Agendamento excluído.','success')
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
@role_required('tecnico','adm_biocognitiva','administrador')
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
