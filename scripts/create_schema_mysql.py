import os
import sys
from sqlmodel import SQLModel, create_engine
from importlib import import_module

# --- asegurar que el root del proyecto esté en sys.path para poder importar "app" ---
HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# ------------------------------------------------------------------------------

MYSQL_URL = os.environ.get("DATABASE_URL")
if not MYSQL_URL:
    print("ERROR: define la variable de entorno DATABASE_URL antes de ejecutar")
    print(r'Ejemplo: set DATABASE_URL=mysql+pymysql://root:root@localhost:3306/mini_pos_db')
    sys.exit(1)

print("Usando DATABASE_URL:", MYSQL_URL)

# importa app.models (ahora debería resolverse porque añadimos ROOT a sys.path)
try:
    models = import_module("app.models")
except Exception as e:
    print("ERROR importando app.models:", e)
    print("Comprueba que el archivo backend\\app\\models.py existe y que estás ejecutando desde backend")
    sys.exit(1)

engine = create_engine(MYSQL_URL, pool_pre_ping=True, echo=True)
print("Creando tablas en la base de datos destino (si no existen)...")
SQLModel.metadata.create_all(engine)
print("Hecho: tablas creadas/verificadas.")