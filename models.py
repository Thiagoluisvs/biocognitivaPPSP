"""
BiocognitivaPPSP - Database Models
5 Perfis: Supervisor, Colaborador, Técnico Biocognitiva, ADM Biocognitiva, Administrador Geral
"""
import sqlite3, os, json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'biocognitiva.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
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
        role TEXT NOT NULL DEFAULT 'colaborador' CHECK(role IN ('supervisor','colaborador','tecnico','adm_biocognitiva','administrador')),
        cpf TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '',
        funcao TEXT DEFAULT '', data_admissao TEXT DEFAULT '',
        empresa TEXT DEFAULT '', active INTEGER DEFAULT 1,
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
        FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (registered_by) REFERENCES users(id)
    )''')

    # Scheduling collections (tab 4 - Agendar coleta/atendimento)
    c.execute('''CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        motivo TEXT NOT NULL CHECK(motivo IN ('admissao','periodico','aleatorio','acidente','suspeita_justificada')),
        data_coleta DATE NOT NULL, horario_coleta TEXT NOT NULL,
        local_coleta TEXT NOT NULL CHECK(local_coleta IN ('biocognitiva','in_company')),
        tipo_exame TEXT NOT NULL CHECK(tipo_exame IN ('alcoolemia','toxicologico_queratina','toxicologico_urina')),
        status TEXT DEFAULT 'agendado' CHECK(status IN ('agendado','realizado','falta','cancelado')),
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
        status TEXT DEFAULT 'agendado' CHECK(status IN ('agendado','realizado','cancelado')),
        agendado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (agendado_por) REFERENCES users(id)
    )''')

    # Exam results (tab 6 - Resultados de exames)
    c.execute('''CREATE TABLE IF NOT EXISTS resultados_exames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, agendamento_id INTEGER,
        resultado TEXT DEFAULT 'pendente' CHECK(resultado IN ('pendente','negativo','positivo','inconclusivo')),
        observacao TEXT DEFAULT '',
        foto_doador TEXT DEFAULT '', foto_bafometro TEXT DEFAULT '',
        foto_termo_consentimento TEXT DEFAULT '', foto_documento TEXT DEFAULT '',
        arquivo_resultado TEXT DEFAULT '',
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

    # Positive sample control (Técnico - Controle positivo)
    c.execute('''CREATE TABLE IF NOT EXISTS controle_positivo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL, resultado_id INTEGER,
        info_amostra TEXT DEFAULT '', remessa_correio TEXT DEFAULT '',
        arquivo_resultado TEXT DEFAULT '', observacao TEXT DEFAULT '',
        registrado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
        FOREIGN KEY (resultado_id) REFERENCES resultados_exames(id),
        FOREIGN KEY (registrado_por) REFERENCES users(id)
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
    ]
    for k, v, d in defaults:
        c.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', (k, v, d))

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

    # Demo appointments
    today = datetime.now().strftime('%Y-%m-%d')
    agends = [
        (1, 'periodico', today, '08:00', 'biocognitiva', 'toxicologico_urina', 'agendado', 2),
        (2, 'admissao', today, '09:00', 'biocognitiva', 'alcoolemia', 'agendado', 2),
        (3, 'aleatorio', today, '10:00', 'in_company', 'toxicologico_queratina', 'realizado', 2),
    ]
    for cid, mot, dt, hr, loc, tp, st, by in agends:
        c.execute('''INSERT INTO agendamentos (colaborador_id, motivo, data_coleta, horario_coleta, local_coleta, tipo_exame, status, agendado_por)
            VALUES (?,?,?,?,?,?,?,?)''', (cid, mot, dt, hr, loc, tp, st, by))

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
    seed_demo_data()
