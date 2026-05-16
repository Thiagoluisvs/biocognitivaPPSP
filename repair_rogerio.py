
import sqlite3
import json

def repair():
    db = sqlite3.connect('biocognitivaPPSP2/biocognitiva.db')
    db.row_factory = sqlite3.Row
    
    # 1. Encontrar o usuário Rogerio
    email_rogerio = 'rogerio.ribeiro@gruponovavia.com.br'
    user = db.execute('SELECT * FROM users WHERE email = ?', (email_rogerio,)).fetchone()
    
    if not user:
        print(f"Usuário {email_rogerio} não encontrado no banco biocognitiva.db")
        # Tentar procurar por nome
        user = db.execute("SELECT * FROM users WHERE name LIKE '%Rogerio%'").fetchone()
        if user:
            print(f"Encontrado usuário similar: {user['name']} ({user['email']})")
            email_rogerio = user['email']
    
    if user:
        print(f"Reparando permissões para {user['name']}...")
        try:
            perms = json.loads(user['permissions'] or '{}')
        except:
            perms = {}
            
        # Garantir acesso aos módulos solicitados
        perms['faltas'] = 'admin'
        perms['controle_positivo'] = 'admin'
        
        db.execute('UPDATE users SET permissions = ? WHERE id = ?', (json.dumps(perms), user['id']))
        db.commit()
        print("Permissões de Faltas e Eventos Impeditivos (Controle Positivo) atualizadas para 'admin'.")
    
    # 2. Atualizar todos os supervisores para garantir que tenham esses acessos
    print("\nVerificando todos os supervisores...")
    supervisors = db.execute("SELECT * FROM users WHERE role = 'supervisor'").fetchall()
    for s in supervisors:
        try:
            p = json.loads(s['permissions'] or '{}')
        except:
            p = {}
            
        changed = False
        if p.get('faltas') != 'admin':
            p['faltas'] = 'admin'
            changed = True
        if p.get('controle_positivo') != 'admin':
            p['controle_positivo'] = 'admin'
            changed = True
            
        if changed:
            db.execute('UPDATE users SET permissions = ? WHERE id = ?', (json.dumps(p), s['id']))
            print(f"Permissões atualizadas para supervisor: {s['name']} ({s['email']})")
    
    db.commit()
    db.close()
    print("\nReparo concluído.")

if __name__ == '__main__':
    repair()
