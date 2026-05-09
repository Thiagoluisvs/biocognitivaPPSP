import sqlite3
from werkzeug.security import generate_password_hash

def setup_admin():
    db = sqlite3.connect('biocognitiva.db')
    db.row_factory = sqlite3.Row
    
    # Check if admin exists
    admin = db.execute('SELECT * FROM users WHERE email=?', ('admin@biocognitiva.com.br',)).fetchone()
    
    if not admin:
        print("Creating admin user...")
        db.execute(
            'INSERT INTO users (name, email, password_hash, role, active) VALUES (?, ?, ?, ?, ?)',
            ('Administrador', 'admin@biocognitiva.com.br', generate_password_hash('admin123', method='pbkdf2:sha256'), 'administrador', 1)
        )
        db.commit()
        print("Admin user created successfully!")
    else:
        print("Admin user already exists.")
        # Ensure password is correct
        db.execute(
            'UPDATE users SET password_hash=?, role=?, active=? WHERE email=?',
            (generate_password_hash('admin123', method='pbkdf2:sha256'), 'administrador', 1, 'admin@biocognitiva.com.br')
        )
        db.commit()
        print("Admin user credentials updated.")
    
    db.close()

if __name__ == "__main__":
    setup_admin()
