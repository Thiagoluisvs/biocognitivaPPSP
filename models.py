"""
BiocognitivaPPSP - Database Models
5 Perfis: Supervisor, Colaborador, Técnico Biocognitiva, ADM Biocognitiva, Administrador Geral
"""
import sqlite3, os, json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'biocognitiva.db')

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users - 5 roles
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'colaborador' CHECK(role IN ('supervisor','colaborador','tecnico','adm_biocognitiva','administrador','super_admin')),
        cpf TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '',
        funcao TEXT DEFAULT '', data_admissao TEXT DEFAULT '',
        empresa TEXT DEFAULT '', active INTEGER DEFAULT 1,
        last_login TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Institutional documents (Supervisor/ADM/Admin tabs 1 & 2)
    c.execute('''CREATE TABLE IF NOT EXISTS institutional_docs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL CHECK(category IN ('institucional','ppsp','contrato','alvara','certificacao','representante_legal','especialista','aparelho')),
        title TEXT NOT NULL, description TEXT DEFAULT '',
        filename TEXT NOT NULL, original_filename TEXT NOT NULL, file_size INTEGER DEFAULT 0,
        uploaded_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (uploaded_by) REFERENCES users(id)
    )''')

    # Collaborator registry (tab 3 - Cadastro de Colaborador)
    c.execute('''CREATE TABLE IF NOT EXISTS colaboradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT NOT NULL, cpf TEXT NOT NULL,
        endereco TEXT DEFAULT '', funcao TEXT DEFAULT 'ARSO',
        data_admissao TEXT DEFAULT '', telefone TEXT DEFAULT '', email TEXT DEFAULT '',
        empresa TEXT DEFAULT '', status TEXT DEFAULT 'ativo' CHECK(status IN ('ativo','inativo','afastado')),
        registered_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_by INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (registered_by) REFERENCES users(id), FOREIGN KEY (updated_by) REFERENCES users(id)
    )''')

    # Scheduling — release 2.0: exames em JSON (mínimo 2 de 3 tipos no app)
    c.execute('''CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        motivo TEXT NOT NULL,
        data_coleta DATE NOT NULL, horario_coleta TEXT NOT NULL,
        local_coleta TEXT NOT NULL CHECK(local_coleta IN ('biocognitiva','in_company')),
        exames TEXT NOT NULL DEFAULT '[]',
        st_urina TEXT DEFAULT 'agendado',
        st_queratina TEXT DEFAULT 'agendado',
        st_alcoolemia TEXT DEFAULT 'agendado',
        observacao TEXT DEFAULT '',
        agendado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (agendado_por) REFERENCES users(id)
    )''')

    # Training scheduling (tab 5 - Agendar treinamento)
    c.execute('''CREATE TABLE IF NOT EXISTS treinamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER, titulo TEXT NOT NULL,
        motivo TEXT NOT NULL CHECK(motivo IN ('admissao','periodico')),
        tipo TEXT DEFAULT 'in_company' CHECK(tipo IN ('in_company','online','presencial')),
        data_treinamento DATE, horario TEXT DEFAULT '',
        arquivo_gravacao TEXT DEFAULT '',
        status TEXT DEFAULT 'agendado' CHECK(status IN ('agendado','realizado','cancelado')),
        agendado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (agendado_por) REFERENCES users(id)
    )''')

    # Exam results (tab 6 - Resultados de exames)
    c.execute('''CREATE TABLE IF NOT EXISTS resultados_exames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, agendamento_id INTEGER,
        data_coleta TEXT DEFAULT '',
        res_alcoolemia TEXT DEFAULT 'pendente',
        res_urina TEXT DEFAULT 'pendente',
        res_queratina TEXT DEFAULT 'pendente',
        observacao TEXT DEFAULT '',
        foto_doador TEXT DEFAULT '', foto_bafometro TEXT DEFAULT '',
        foto_termo_consentimento TEXT DEFAULT '', foto_documento TEXT DEFAULT '',
        arquivo_resultado TEXT DEFAULT '',
        arquivo_urina TEXT DEFAULT '', arquivo_queratina TEXT DEFAULT '',
        lancado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id),
        FOREIGN KEY (lancado_por) REFERENCES users(id)
    )''')

    # Program reports (tab 7 - Relatórios do Programa)
    c.execute('''CREATE TABLE IF NOT EXISTS relatorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL, descricao TEXT DEFAULT '', categoria TEXT DEFAULT 'geral',
        filename TEXT NOT NULL, original_filename TEXT NOT NULL, file_size INTEGER DEFAULT 0,
        uploaded_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (uploaded_by) REFERENCES users(id)
    )''')

    # Service requests (tab 8 - Agendar serviços / Requerimentos)
    c.execute('''CREATE TABLE IF NOT EXISTS servicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL CHECK(tipo IN ('coleta_in_company','treinamento_in_company','relatorio_especifico','auditoria','outro')),
        titulo TEXT NOT NULL, descricao TEXT DEFAULT '',
        documento_anexo TEXT DEFAULT '', documento_resposta TEXT DEFAULT '',
        status TEXT DEFAULT 'pendente' CHECK(status IN ('pendente','em_andamento','concluido','cancelado')),
        solicitado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (solicitado_por) REFERENCES users(id)
    )''')

    # Collaborator evaluations/quizzes (tab 9 - Avaliações)
    c.execute('''CREATE TABLE IF NOT EXISTS avaliacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL, descricao TEXT DEFAULT '',
        nota_minima REAL DEFAULT 8.0, nota_maxima REAL DEFAULT 10.0,
        max_tentativas INTEGER DEFAULT 2,
        video_aula_url TEXT DEFAULT '', active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS avaliacao_questoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        avaliacao_id INTEGER NOT NULL,
        pergunta TEXT NOT NULL,
        tipo TEXT DEFAULT 'multiple_choice' CHECK(tipo IN ('multiple_choice','true_false')),
        opcoes TEXT DEFAULT '[]', resposta_correta TEXT NOT NULL,
        pontos REAL DEFAULT 1.0, ordem INTEGER DEFAULT 0,
        FOREIGN KEY (avaliacao_id) REFERENCES avaliacoes(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS avaliacao_tentativas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        avaliacao_id INTEGER NOT NULL, colaborador_id INTEGER NOT NULL,
        respostas TEXT DEFAULT '{}', nota REAL DEFAULT 0, nota_maxima REAL DEFAULT 10,
        aprovado INTEGER DEFAULT 0, tentativa_num INTEGER DEFAULT 1,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (avaliacao_id) REFERENCES avaliacoes(id),
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
    )''')

    # Random draw (tab 10 - Sorteio Aleatório)
    c.execute('''CREATE TABLE IF NOT EXISTS sorteios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL, quantidade INTEGER DEFAULT 1,
        colaboradores_sorteados TEXT DEFAULT '[]',
        realizado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (realizado_por) REFERENCES users(id)
    )''')

    # Financial (ADM Biocognitiva / Administrador - Financeiro)
    c.execute('''CREATE TABLE IF NOT EXISTS financeiro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL CHECK(tipo IN ('boleto','nota_fiscal','tabela_precos','outro')),
        titulo TEXT NOT NULL, descricao TEXT DEFAULT '',
        filename TEXT NOT NULL, original_filename TEXT NOT NULL, file_size INTEGER DEFAULT 0,
        uploaded_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (uploaded_by) REFERENCES users(id)
    )''')

    # Absence reports (Técnico - Relatório de faltas)
    c.execute('''CREATE TABLE IF NOT EXISTS faltas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, data_falta DATE NOT NULL,
        agendamento_id INTEGER, observacao TEXT DEFAULT '',
        registrado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id),
        FOREIGN KEY (registrado_por) REFERENCES users(id)
    )''')

    # Eventos impeditivos (ex-controle positivo)
    c.execute('''CREATE TABLE IF NOT EXISTS controle_positivo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, resultado_id INTEGER,
        tipo_evento TEXT NOT NULL DEFAULT 'positivo_amostra' CHECK(tipo_evento IN (
            'positivo_amostra','agendamento_avaliacao_psicologica','agendamento_medico_revisor')),
        data_agendamento TEXT DEFAULT '', horario_agendamento TEXT DEFAULT '',
        info_amostra TEXT DEFAULT '', remessa_correio TEXT DEFAULT '',
        arquivo_resultado TEXT DEFAULT '', observacao TEXT DEFAULT '',
        registrado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (resultado_id) REFERENCES resultados_exames(id),
        FOREIGN KEY (registrado_por) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS clientes_empresa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razao_social TEXT NOT NULL, nome_fantasia TEXT DEFAULT '', cnpj TEXT DEFAULT '',
        cidade TEXT DEFAULT '', contato_nome TEXT DEFAULT '',
        telefone TEXT DEFAULT '', email TEXT DEFAULT '', observacao TEXT DEFAULT '',
        registered_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (registered_by) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS subcontratadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_fantasia TEXT NOT NULL, razao_social TEXT DEFAULT '', cnpj TEXT DEFAULT '',
        contato_nome TEXT DEFAULT '', telefone TEXT DEFAULT '', email TEXT DEFAULT '',
        observacao TEXT DEFAULT '',
        registered_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (registered_by) REFERENCES users(id)
    )''')

    # Rastreabilidade positivas (ADM tab 10)
    c.execute('''CREATE TABLE IF NOT EXISTS rastreabilidade (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, resultado_id INTEGER,
        descricao TEXT DEFAULT '', status TEXT DEFAULT 'em_acompanhamento',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (resultado_id) REFERENCES resultados_exames(id)
    )''')

    # Prontuários médicos (ADM tab 11)
    c.execute('''CREATE TABLE IF NOT EXISTS prontuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        titulo TEXT NOT NULL, descricao TEXT DEFAULT '',
        filename TEXT DEFAULT '', original_filename TEXT DEFAULT '',
        registrado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (registrado_por) REFERENCES users(id)
    )''')

    # Training videos for collaborators
    c.execute('''CREATE TABLE IF NOT EXISTS video_aulas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL, descricao TEXT DEFAULT '',
        video_url TEXT NOT NULL, ordem INTEGER DEFAULT 0,
        duracao_minutos INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Video watch progress
    c.execute('''CREATE TABLE IF NOT EXISTS video_progresso (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, video_id INTEGER NOT NULL,
        assistido INTEGER DEFAULT 0, segundos_assistidos INTEGER DEFAULT 0,
        completed_at TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (video_id) REFERENCES video_aulas(id),
        UNIQUE(colaborador_id, video_id)
    )''')

    # Platform settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL, value TEXT NOT NULL,
        description TEXT DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    defaults = [
        ('nota_minima', '8.0', 'Nota mínima para aprovação na avaliação'),
        ('nota_maxima', '10.0', 'Nota máxima da avaliação'),
        ('max_tentativas', '2', 'Máx. tentativas na avaliação'),
        ('platform_name', 'BiocognitivaPPSP', 'Nome da plataforma'),
        ('num_questoes_avaliacao', '10', 'Número de questões por avaliação'),
        ('backup_auto_enabled', '0', 'Ativar backup automático (0=Não, 1=Sim)'),
        ('backup_frequency', 'daily', 'Frequência do backup (6h, 12h, daily, weekly, monthly)'),
        ('backup_retention_days', '30', 'Dias para manter os backups'),
        ('backup_last_run', '', 'Última execução do backup automático'),
    ]
    for k, v, d in defaults:
        c.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', (k, v, d))

    # Seed default admin if no users exist
    if not c.execute('SELECT id FROM users LIMIT 1').fetchone():
        c.execute(
            'INSERT INTO users (name, email, password_hash, role, active) VALUES (?, ?, ?, ?, ?)',
            ('Administrador Geral', 'admin@biocognitiva.com.br', generate_password_hash('admin123', method='pbkdf2:sha256'), 'administrador', 1)
        )

    conn.commit()
    conn.close()
    migrate_schema()


def _table_columns(cursor, table):
    try:
        return {row[1] for row in cursor.execute('PRAGMA table_info(%s)' % table).fetchall()}
    except sqlite3.OperationalError:
        return set()


def _migrate_agendamentos_v2(conn):
    c = conn.cursor()
    rows = c.execute('SELECT * FROM agendamentos').fetchall()
    c.execute('PRAGMA foreign_keys=OFF')
    c.execute('DROP TABLE IF EXISTS agendamentos_new')
    c.execute('''CREATE TABLE agendamentos_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        motivo TEXT NOT NULL,
        data_coleta DATE NOT NULL, horario_coleta TEXT NOT NULL,
        local_coleta TEXT NOT NULL CHECK(local_coleta IN ('biocognitiva','in_company')),
        exames TEXT NOT NULL DEFAULT '[]',
        status TEXT DEFAULT 'agendado' CHECK(status IN ('agendado','realizado','falta','cancelado')),
        observacao TEXT DEFAULT '',
        agendado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (agendado_por) REFERENCES users(id)
    )''')
    motmap = {
        'admissao': 'exame_admissional',
        'periodico': 'exame_acompanhamento',
        'aleatorio': 'exame_aleatorio',
        'acidente': 'exame_pos_acidente',
        'suspeita_justificada': 'exame_aleatorio',
    }
    for r in rows:
        old_m = r['motivo']
        new_m = motmap.get(old_m, old_m)
        tipo = r['tipo_exame']
        exames_json = json.dumps([tipo] if tipo else ['toxicologico_urina'])
        obs = r['observacao'] if r['observacao'] is not None else ''
        c.execute(
            '''INSERT INTO agendamentos_new (id, colaborador_id, motivo, data_coleta, horario_coleta, local_coleta, exames, status, observacao, agendado_por, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (r['id'], r['colaborador_id'], new_m, r['data_coleta'], r['horario_coleta'], r['local_coleta'], exames_json, r['status'], obs, r['agendado_por'], r['created_at']),
        )
    c.execute('DROP TABLE agendamentos')
    c.execute('ALTER TABLE agendamentos_new RENAME TO agendamentos')
    c.execute('PRAGMA foreign_keys=ON')
    try:
        mx_row = c.execute('SELECT MAX(id) FROM agendamentos').fetchone()
        mx = int(mx_row[0]) if mx_row and mx_row[0] is not None else 0
        c.execute("DELETE FROM sqlite_sequence WHERE name='agendamentos'")
        if mx > 0:
            c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('agendamentos', ?)", (mx,))
    except sqlite3.OperationalError:
        pass
    conn.commit()


def migrate_schema():
    conn = get_db()
    c = conn.cursor()
    ac = _table_columns(c, 'agendamentos')
    if ac and 'exames' not in ac and 'tipo_exame' in ac:
        _migrate_agendamentos_v2(conn)
        c = conn.cursor()
        ac = _table_columns(c, 'agendamentos')
    if ac and 'exames' not in ac:
        try:
            c.execute("ALTER TABLE agendamentos ADD COLUMN exames TEXT NOT NULL DEFAULT '[]'")
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()

    tc = _table_columns(c, 'treinamentos')
    if tc and 'arquivo_gravacao' not in tc:
        try:
            c.execute('ALTER TABLE treinamentos ADD COLUMN arquivo_gravacao TEXT DEFAULT ""')
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()

    rc = _table_columns(c, 'resultados_exames')
    if rc and 'data_coleta' not in rc:
        try:
            c.execute('ALTER TABLE resultados_exames ADD COLUMN data_coleta TEXT DEFAULT ""')
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()

    cp = _table_columns(c, 'controle_positivo')
    if cp:
        for col, decl in (
            ('tipo_evento', "ALTER TABLE controle_positivo ADD COLUMN tipo_evento TEXT DEFAULT 'positivo_amostra'"),
            ('data_agendamento', 'ALTER TABLE controle_positivo ADD COLUMN data_agendamento TEXT DEFAULT ""'),
            ('horario_agendamento', 'ALTER TABLE controle_positivo ADD COLUMN horario_agendamento TEXT DEFAULT ""'),
        ):
            if col not in cp:
                try:
                    c.execute(decl)
                    conn.commit()
                except sqlite3.OperationalError:
                    conn.rollback()
                cp.add(col)

    for create in (
        '''CREATE TABLE IF NOT EXISTS clientes_empresa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razao_social TEXT NOT NULL, nome_fantasia TEXT DEFAULT '', cnpj TEXT DEFAULT '',
        cidade TEXT DEFAULT '', contato_nome TEXT DEFAULT '',
        telefone TEXT DEFAULT '', email TEXT DEFAULT '', observacao TEXT DEFAULT '',
        registered_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (registered_by) REFERENCES users(id)
    )''',
        '''CREATE TABLE IF NOT EXISTS subcontratadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_fantasia TEXT NOT NULL, razao_social TEXT DEFAULT '', cnpj TEXT DEFAULT '',
        contato_nome TEXT DEFAULT '', telefone TEXT DEFAULT '', email TEXT DEFAULT '',
        observacao TEXT DEFAULT '',
        registered_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (registered_by) REFERENCES users(id)
    )''',
        '''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL CHECK(action IN ('CREATE','UPDATE','DELETE')),
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        old_values TEXT DEFAULT '{}',
        new_values TEXT DEFAULT '{}',
        changes TEXT DEFAULT '',
        ip_address TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''',
    ):
        c.execute(create)
    
    # Migrate colaboradores table to add updated_at and updated_by columns
    colab_cols = _table_columns(c, 'colaboradores')
    if colab_cols and 'updated_at' not in colab_cols:
        try:
            c.execute('ALTER TABLE colaboradores ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    
    if colab_cols and 'updated_by' not in colab_cols:
        try:
            c.execute('ALTER TABLE colaboradores ADD COLUMN updated_by INTEGER REFERENCES users(id)')
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    
    # Add last_login to users
    user_cols = _table_columns(c, 'users')
    if user_cols and 'last_login' not in user_cols:
        try:
            c.execute('ALTER TABLE users ADD COLUMN last_login TIMESTAMP')
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    
    conn.commit()
    conn.close()


def seed_demo_data():
    conn = get_db()
    c = conn.cursor()
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    M = 'pbkdf2:sha256'
    users = [
        ('Administrador Geral', 'admin@biocognitiva.com.br', generate_password_hash('admin123', method=M), 'administrador'),
        ('Carlos Silva - Supervisor', 'supervisor@novavia.com.br', generate_password_hash('super123', method=M), 'supervisor'),
        ('Dr. Ana Santos - ADM Bio', 'adm@biocognitiva.com.br', generate_password_hash('adm123', method=M), 'adm_biocognitiva'),
        ('Técnico João', 'tecnico@biocognitiva.com.br', generate_password_hash('tec123', method=M), 'tecnico'),
        ('Pedro Oliveira', 'pedro@novavia.com.br', generate_password_hash('colab123', method=M), 'colaborador'),
    ]
    for n, e, p, r in users:
        c.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)', (n, e, p, r))

    # Demo collaborators
    colabs = [
        ('Maria Costa', '111.222.333-44', 'Rua A, 100', 'Piloto', '2024-01-15', '(11)99999-0001', 'maria@novavia.com.br', 'NOVAVIA', 2),
        ('José Santos', '222.333.444-55', 'Rua B, 200', 'Copiloto', '2023-06-20', '(11)99999-0002', 'jose@novavia.com.br', 'NOVAVIA', 2),
        ('Ana Ferreira', '333.444.555-66', 'Rua C, 300', 'Mecânico', '2024-03-10', '(11)99999-0003', 'ana@novavia.com.br', 'NOVAVIA', 2),
        ('Ricardo Lima', '444.555.666-77', 'Rua D, 400', 'Comissário', '2023-11-01', '(11)99999-0004', 'ricardo@novavia.com.br', 'NOVAVIA', 2),
        ('Lucia Almeida', '555.666.777-88', 'Rua E, 500', 'Piloto', '2024-05-01', '(11)99999-0005', 'lucia@novavia.com.br', 'NOVAVIA', 2),
    ]
    for n, cpf, end, func, adm, tel, em, emp, reg in colabs:
        c.execute('''INSERT INTO colaboradores (name, cpf, endereco, funcao, data_admissao, telefone, email, empresa, registered_by)
            VALUES (?,?,?,?,?,?,?,?,?)''', (n, cpf, end, func, adm, tel, em, emp, reg))

    # Demo appointments (mínimo 2 exames)
    today = datetime.now().strftime('%Y-%m-%d')
    agends = [
        (1, 'exame_acompanhamento', today, '08:00', 'biocognitiva', json.dumps(['toxicologico_urina', 'toxicologico_queratina']), 'agendado', 'agendado', 'agendado', 2),
        (2, 'exame_admissional', today, '09:00', 'biocognitiva', json.dumps(['alcoolemia', 'toxicologico_urina']), 'agendado', 'agendado', 'agendado', 2),
        (3, 'exame_aleatorio', today, '10:00', 'in_company', json.dumps(['toxicologico_queratina', 'alcoolemia']), 'realizado', 'realizado', 'realizado', 2),
    ]
    for cid, mot, dt, hr, loc, exj, st_u, st_q, st_a, by in agends:
        c.execute(
            '''INSERT INTO agendamentos (colaborador_id, motivo, data_coleta, horario_coleta, local_coleta, exames, st_urina, st_queratina, st_alcoolemia, agendado_por)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (cid, mot, dt, hr, loc, exj, st_u, st_q, st_a, by),
        )

    # Demo video lessons
    videos = [
        ('Introdução ao PPSP', 'Conceitos fundamentais do Programa de Prevenção de Substâncias Psicoativas', 'https://www.youtube.com/embed/dQw4w9WgXcQ', 1, 30),
        ('Substâncias Monitoradas', 'Classes de substâncias e seus efeitos na aviação', 'https://www.youtube.com/embed/dQw4w9WgXcQ', 2, 25),
        ('Procedimentos de Coleta', 'Protocolos e cadeia de custódia', 'https://www.youtube.com/embed/dQw4w9WgXcQ', 3, 35),
        ('Direitos e Deveres', 'Marco regulatório e responsabilidades', 'https://www.youtube.com/embed/dQw4w9WgXcQ', 4, 20),
    ]
    for t, d, u, o, dur in videos:
        c.execute('INSERT INTO video_aulas (titulo, descricao, video_url, ordem, duracao_minutos) VALUES (?,?,?,?,?)', (t, d, u, o, dur))

    # Demo evaluation with 10 questions
    c.execute('''INSERT INTO avaliacoes (titulo, descricao, nota_minima, nota_maxima, max_tentativas, video_aula_url)
        VALUES (?, ?, 8.0, 10.0, 2, '')''',
        ('Avaliação PPSP - Treinamento Obrigatório', 'Avaliação de conhecimentos sobre o Programa de Prevenção de Substâncias Psicoativas'))

    questions = [
        ('O que significa a sigla PPSP?', json.dumps(['Programa de Proteção Social Permanente','Programa de Prevenção ao uso de Substâncias Psicoativas','Protocolo de Procedimentos de Segurança Pessoal','Plano de Prevenção e Saúde Profissional']), 'Programa de Prevenção ao uso de Substâncias Psicoativas'),
        ('Qual órgão regulamenta o PPSP na aviação civil brasileira?', json.dumps(['ANVISA','ANAC','ANATEL','INMETRO']), 'ANAC'),
        ('Quais substâncias são monitoradas no programa?', json.dumps(['Apenas álcool','Apenas drogas ilícitas','Álcool, anfetaminas, canabinoides, cocaína e opiáceos','Apenas medicamentos controlados']), 'Álcool, anfetaminas, canabinoides, cocaína e opiáceos'),
        ('O que é a cadeia de custódia?', json.dumps(['Processo de descarte de amostras','Documentação que rastreia a amostra da coleta ao resultado','Lista de substâncias detectadas','Protocolo de armazenamento']), 'Documentação que rastreia a amostra da coleta ao resultado'),
        ('Em caso de resultado positivo, o que acontece?', json.dumps(['Demissão imediata','Encaminhamento para avaliação médica e acompanhamento','Nenhuma ação','Suspensão sem acompanhamento']), 'Encaminhamento para avaliação médica e acompanhamento'),
        ('Qual material biológico é mais utilizado nos testes?', json.dumps(['Sangue','Saliva','Urina','Cabelo']), 'Urina'),
        ('A coleta aleatória é obrigatória no PPSP?', json.dumps(['Verdadeiro','Falso']), 'Verdadeiro'),
        ('Qual o objetivo principal do PPSP?', json.dumps(['Punir colaboradores','Garantir a segurança operacional','Reduzir custos','Cumprir formalidade burocrática']), 'Garantir a segurança operacional'),
        ('O teste de confirmação é necessário quando?', json.dumps(['Sempre que o teste de triagem for positivo','Apenas por decisão judicial','Nunca','Apenas para pilotos']), 'Sempre que o teste de triagem for positivo'),
        ('O colaborador tem direito a segunda coleta?', json.dumps(['Sim, dentro do prazo regulamentar','Não, nunca','Apenas se for piloto','Apenas com ordem judicial']), 'Sim, dentro do prazo regulamentar'),
    ]
    for i, (p, opts, resp) in enumerate(questions):
        c.execute('''INSERT INTO avaliacao_questoes (avaliacao_id, pergunta, tipo, opcoes, resposta_correta, pontos, ordem)
            VALUES (1, ?, 'multiple_choice', ?, ?, 1.0, ?)''', (p, opts, resp, i+1))

    conn.commit()
    conn.close()
    print("✅ BiocognitivaPPSP demo data seeded!")

if __name__ == '__main__':
    init_db()
