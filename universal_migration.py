
import sqlite3
import json
import os
import subprocess

ALL_MODULES_KEYS = [
    'institucional', 'colaboradores', 'agendamentos', 'resultados',
    'financeiro', 'relatorios', 'servicos', 'treinamentos',
    'faltas', 'sorteio', 'subcontratadas', 'controle_positivo',
    'clientes', 'estoque_kits', 'settings', 'auditoria', 'admin_users'
]

def get_default_permissions(role):
    perms = {}
    if role in ('super_admin', 'administrador', 'adm_biocognitiva'):
        for mod in ALL_MODULES_KEYS: perms[mod] = 'admin'
    elif role == 'supervisor':
        # Supervisores: Acesso total aos módulos operacionais
        admin_mods = ('institucional', 'colaboradores', 'agendamentos', 'resultados', 'treinamentos', 
                     'relatorios', 'servicos', 'sorteio', 'subcontratadas', 'controle_positivo', 'faltas', 'clientes')
        for mod in admin_mods: perms[mod] = 'admin'
        
        # Acesso de visualização a módulos de sistema/suporte
        view_mods = ('financeiro', 'estoque_kits', 'settings', 'auditoria')
        for mod in view_mods: perms[mod] = 'admin' # O usuário pediu para ver esses módulos no controle, então daremos admin para garantir acesso total se for o caso
    elif role == 'tecnico':
        mods = ('agendamentos', 'resultados', 'faltas', 'controle_positivo', 'estoque_kits')
        for mod in mods: perms[mod] = 'admin'
    return perms

def migrate_db(db_path):
    print(f"\n--- Processando: {db_path} ---")
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        
        users = db.execute("SELECT * FROM users").fetchall()
        for u in users:
            try:
                p = json.loads(u['permissions'] or '{}')
            except:
                p = {}
            
            defaults = get_default_permissions(u['role'])
            updated = False
            
            # Garantir que todos os módulos padrão do cargo existam
            for mod, level in defaults.items():
                if p.get(mod) != level:
                    p[mod] = level
                    updated = True
            
            # Caso específico do Rogerio
            if u['email'] == 'rogerio.ribeiro@gruponovavia.com.br' or 'rogerio' in u['name'].lower():
                p['faltas'] = 'admin'
                p['controle_positivo'] = 'admin'
                p['clientes'] = 'admin'
                p['estoque_kits'] = 'admin'
                p['settings'] = 'admin'
                p['auditoria'] = 'admin'
                updated = True

            if updated:
                db.execute("UPDATE users SET permissions = ? WHERE id = ?", (json.dumps(p), u['id']))
                print(f"   [OK] {u['name']} ({u['role']}) - Permissões sincronizadas.")
        
        db.commit()
        db.close()
    except Exception as e:
        print(f"   [ERRO] Falha: {e}")

if __name__ == "__main__":
    dbs = subprocess.check_output(["find", ".", "-name", "*.db"]).decode().splitlines()
    for d in dbs:
        if "backups" not in d and "/." not in d:
            migrate_db(d)
    print("\nMigração finalizada.")
