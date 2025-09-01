import os
from sqlalchemy import create_engine, inspect, text

url = os.environ.get("DATABASE_URL")
print("DATABASE_URL:", url)
if not url:
    raise SystemExit("ERROR: DATABASE_URL no definido en el entorno")

engine = create_engine(url, pool_pre_ping=True, echo=True)

print("Conectando y listando tablas existentes...")
insp = inspect(engine)
tables = insp.get_table_names()
print("Tablas en la BD destino:", tables)

# prueba simple de creación temporal (no destructiva)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("Consulta de prueba OK")