"""BiocognitivaPPSP - Main App"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
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
    if 'user_id' not in session: return None
    db=get_db(); u=db.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); db.close()
    return u

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
    u=get_user(); db=get_db(); d={}
    if u['role']=='colaborador':
        colab=db.execute('SELECT * FROM colaboradores WHERE email=?',(u['email'],)).fetchone()
        d['colab']=colab
        d['videos']=db.execute('SELECT * FROM video_aulas ORDER BY ordem').fetchall()
        d['avaliacoes']=db.execute('SELECT * FROM avaliacoes WHERE active=1').fetchall()
        if colab:
            d['tentativas']=db.execute('SELECT * FROM avaliacao_tentativas WHERE colaborador_id=? ORDER BY completed_at DESC',(colab['id'],)).fetchall()
    elif u['role']=='supervisor':
        d['colaboradores']=db.execute('SELECT * FROM colaboradores ORDER BY name').fetchall()
        d['agendamentos']=db.execute('SELECT a.*,c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id ORDER BY a.data_coleta DESC LIMIT 10').fetchall()
        d['total_colabs']=db.execute('SELECT COUNT(*) as c FROM colaboradores').fetchone()['c']
        d['total_agend']=db.execute('SELECT COUNT(*) as c FROM agendamentos').fetchone()['c']
    elif u['role']=='tecnico':
        d['agenda_hoje']=db.execute("SELECT a.*,c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id WHERE a.data_coleta=date('now') ORDER BY a.horario_coleta",()).fetchall()
        d['total_hoje']=len(d['agenda_hoje'])
    elif u['role']=='adm_biocognitiva':
        d['total_colabs']=db.execute('SELECT COUNT(*) as c FROM colaboradores').fetchone()['c']
        d['total_agend']=db.execute('SELECT COUNT(*) as c FROM agendamentos').fetchone()['c']
        d['total_resultados']=db.execute('SELECT COUNT(*) as c FROM resultados_exames').fetchone()['c']
        d['agendamentos']=db.execute('SELECT a.*,c.name as colab_name FROM agendamentos a JOIN colaboradores c ON a.colaborador_id=c.id ORDER BY a.data_coleta DESC LIMIT 10').fetchall()
    else:
        d['total_users']=db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        d['total_colabs']=db.execute('SELECT COUNT(*) as c FROM colaboradores').fetchone()['c']
        d['total_agend']=db.execute('SELECT COUNT(*) as c FROM agendamentos').fetchone()['c']
        d['users']=db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('dashboard.html', user=u, data=d)

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
        db=get_db()
        db.execute('''INSERT INTO colaboradores (name,cpf,endereco,funcao,data_admissao,telefone,email,empresa,registered_by)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (request.form['name'],request.form['cpf'],request.form.get('endereco',''),
             request.form.get('funcao','ARSO'),request.form.get('data_admissao',''),
             request.form.get('telefone',''),request.form.get('email',''),
             request.form.get('empresa',''),u['id']))
        db.commit(); db.close(); flash('Colaborador cadastrado!','success')
        return redirect(url_for('colaboradores'))
    return render_template('colaborador_form.html', user=u, colab=None)

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
    u=get_user(); db=get_db()
    db.execute('''INSERT INTO agendamentos (colaborador_id,motivo,data_coleta,horario_coleta,local_coleta,tipo_exame,agendado_por)
        VALUES (?,?,?,?,?,?,?)''',
        (request.form['colaborador_id'],request.form['motivo'],request.form['data_coleta'],
         request.form['horario_coleta'],request.form['local_coleta'],request.form['tipo_exame'],u['id']))
    db.commit(); db.close(); flash('Agendamento criado!','success')
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
    u=get_user(); db=get_db()
    db.execute('''INSERT INTO treinamentos (colaborador_id,titulo,motivo,tipo,data_treinamento,horario,agendado_por)
        VALUES (?,?,?,?,?,?,?)''',
        (request.form.get('colaborador_id'),request.form['titulo'],request.form['motivo'],
         request.form.get('tipo','in_company'),request.form.get('data_treinamento',''),
         request.form.get('horario',''),u['id']))
    db.commit(); db.close(); flash('Treinamento agendado!','success')
    return redirect(url_for('treinamentos'))

# === RESULTADOS ===
@app.route('/resultados')
@login_required
def resultados():
    u=get_user(); db=get_db()
    search=request.args.get('search','')
    q='SELECT r.*,c.name as colab_name FROM resultados_exames r JOIN colaboradores c ON r.colaborador_id=c.id'
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
    db.execute('''INSERT INTO resultados_exames (colaborador_id,agendamento_id,resultado,observacao,foto_doador,foto_bafometro,foto_termo_consentimento,foto_documento,arquivo_resultado,lancado_por)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (request.form['colaborador_id'],request.form.get('agendamento_id') or None,
         request.form.get('resultado','pendente'),request.form.get('observacao',''),
         foto_doador,foto_baf,foto_termo,foto_doc,arq_res,u['id']))
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
@role_required('supervisor','adm_biocognitiva','administrador')
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
@role_required('supervisor','adm_biocognitiva','administrador')
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
    u=get_user(); arq=''
    if 'arquivo' in request.files and request.files['arquivo'].filename:
        arq,_,_=save_upload(request.files['arquivo'],'documents')
    db=get_db()
    db.execute('INSERT INTO controle_positivo (colaborador_id,info_amostra,remessa_correio,arquivo_resultado,observacao,registrado_por) VALUES (?,?,?,?,?,?)',
        (request.form['colaborador_id'],request.form.get('info_amostra',''),request.form.get('remessa_correio',''),arq,request.form.get('observacao',''),u['id']))
    db.commit(); db.close(); flash('Controle positivo registrado!','success')
    return redirect(url_for('controle_positivo'))

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
    db=get_db(); usr=db.execute('SELECT active FROM users WHERE id=?',(uid,)).fetchone()
    if usr: db.execute('UPDATE users SET active=? WHERE id=?',(0 if usr['active'] else 1, uid)); db.commit()
    db.close(); return redirect(url_for('admin_users'))

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

if __name__=='__main__':
    init_db(); seed_demo_data(); app.run(debug=True,port=5000)
