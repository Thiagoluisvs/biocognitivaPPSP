import paramiko

sql = """
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

CREATE TABLE new_controle_positivo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    colaborador_id INTEGER NOT NULL, resultado_id INTEGER,
    tipo_evento TEXT NOT NULL DEFAULT 'positivo_amostra' CHECK(tipo_evento IN (
        'positivo_amostra','analise_laboratorial','agendamento_avaliacao_psicologica','agendamento_medico_revisor')),
    data_agendamento TEXT DEFAULT '', horario_agendamento TEXT DEFAULT '',
    info_amostra TEXT DEFAULT '', remessa_correio TEXT DEFAULT '',
    arquivo_resultado TEXT DEFAULT '', observacao TEXT DEFAULT '',
    registrado_por INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
    FOREIGN KEY (resultado_id) REFERENCES resultados_exames(id),
    FOREIGN KEY (registrado_por) REFERENCES users(id)
);
INSERT INTO new_controle_positivo SELECT * FROM controle_positivo;
DROP TABLE controle_positivo;
ALTER TABLE new_controle_positivo RENAME TO controle_positivo;

CREATE TABLE new_rastreabilidade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    colaborador_id INTEGER NOT NULL, resultado_id INTEGER,
    descricao TEXT DEFAULT '', status TEXT DEFAULT 'em_acompanhamento',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
    FOREIGN KEY (resultado_id) REFERENCES resultados_exames(id)
);
INSERT INTO new_rastreabilidade SELECT * FROM rastreabilidade;
DROP TABLE rastreabilidade;
ALTER TABLE new_rastreabilidade RENAME TO rastreabilidade;

COMMIT;
PRAGMA foreign_keys=on;
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.24.89.166', username='root', password='Tlvs30862814#')

sftp = ssh.open_sftp()
with sftp.open('/var/www/biocognitiva/fix.sql', 'w') as f:
    f.write(sql)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('sqlite3 /var/www/biocognitiva/biocognitiva.db < /var/www/biocognitiva/fix.sql')
print(stdout.read().decode())
err = stderr.read().decode()
if err: print("ERROR:", err)

ssh.close()
