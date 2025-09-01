import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "..", "dev.db")
db_path = os.path.abspath(db_path)

if not os.path.exists(db_path):
    print("DB no encontrada:", db_path)
    raise SystemExit(1)

# Hacer backup por precaución
backup = db_path + ".bak"
if not os.path.exists(backup):
    import shutil
    shutil.copy(db_path, backup)
    print("Backup creado en", backup)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("PRAGMA table_info('user')")
existing = [r[1] for r in cur.fetchall()]

to_add = [
    ("recovery_email", "TEXT"),
    ("recovery_verified", "INTEGER DEFAULT 0"),
    ("recovery_verification_token", "TEXT"),
    ("recovery_verification_expires", "TEXT"),
    ("reset_token", "TEXT"),
    ("reset_expires", "TEXT"),
]

for name, sql_type in to_add:
    if name in existing:
        print(f"Columna ya existe: {name}")
    else:
        print(f"Añadiendo columna: {name} {sql_type}")
        cur.execute(f"ALTER TABLE user ADD COLUMN {name} {sql_type}")

conn.commit()
conn.close()
print("Migración completada.")