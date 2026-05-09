
import json
import sqlite3
import os
from flask import Flask, render_template, session

# Mock app
app = Flask(__name__, template_folder='templates')
app.secret_key = 'test'
DATABASE = 'biocognitiva.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.template_filter('exames_json_list')
def exames_json_list(s):
    try: return json.loads(s) if s else []
    except: return []

@app.template_filter('label_exame_agendamento')
def label_exame_agendamento(code):
    return code

@app.template_filter('label_motivo_agendamento')
def label_motivo_agendamento(code):
    return code

with app.app_context():
    try:
        db = get_db()
        u = db.execute('SELECT * FROM users LIMIT 1').fetchone()
        if not u:
            print("No user found in DB. Please run setup_admin.py first.")
            exit(1)
        
        u = dict(u)
        print(f"Testing for user: {u['email']} (role: {u['role']})")
        
        # Simulating dashboard logic
        d = {}
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
        
        print("Data dictionary built successfully.")
        
        # Try to render
        with app.test_request_context():
            session['user_id'] = u['id']
            session['role'] = u['role']
            session['name'] = u['name']
            html = render_template('dashboard.html', user=u, data=d)
            print("Template rendered successfully.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
