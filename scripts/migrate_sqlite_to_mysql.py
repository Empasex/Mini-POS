"""
Migra datos desde el SQLite (backend/dev.db) hacia la base MySQL.
Uso (Windows CMD):
  cd d:\mini-pos\backend
  .\.venv\Scripts\activate.bat
  pip install -r requirements.txt
  set DATABASE_URL=mysql+pymysql://USER:PASS@HOST:3306/DBNAME
  python scripts\migrate_sqlite_to_mysql.py

Este script:
 - intenta usar las clases de app.models (SQLModel) para crear esquema y copiar fila a fila;
 - si no encuentra modelos, hace un reflect de SQLite y copia tabla->tabla con inserciones masivas;
 - desactiva/reactiva FOREIGN_KEY_CHECKS en MySQL durante la migración.
"""
import os
import sys
from typing import List, Dict
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from importlib import import_module

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SQLITE_PATH = os.path.join(ROOT, "dev.db")
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

MYSQL_URL = os.environ.get("DATABASE_URL")
if not MYSQL_URL:
    print("ERROR: DATABASE_URL no definido. Ejecuta:")
    print("  set DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname")
    sys.exit(1)

print("Origen (SQLite):", SQLITE_URL)
print("Destino (MySQL):", MYSQL_URL)

# Engines
engine_src = create_engine(SQLITE_URL, connect_args={"check_same_thread": False}, echo=False)
engine_dst = create_engine(MYSQL_URL, echo=True, pool_pre_ping=True)

def try_import_models():
    try:
        models_mod = import_module("app.models")
    except Exception as e:
        print("No se pudo importar app.models:", e)
        return None
    # Detectar clases SQLModel exportadas (User, Product, etc.)
    classes = {}
    for name in dir(models_mod):
        if name.startswith("_"):
            continue
        obj = getattr(models_mod, name)
        # SQLModel classes have metadata and __table__ after metadata creation; accept classes subclassing SQLModel
        try:
            if isinstance(obj, type) and issubclass(obj, SQLModel):
                classes[name] = obj
        except Exception:
            continue
    return classes

def migrate_using_models(classes: Dict[str, type]):
    if not classes:
        print("No se detectaron clases SQLModel en app.models.")
        return False

    print("Clases SQLModel detectadas:", ", ".join(classes.keys()))
    # Crear esquema en destino
    print("Creando/verificando esquema en MySQL usando SQLModel.metadata.create_all...")
    SQLModel.metadata.create_all(engine_dst)
    print("Esquema creado/verificado.")

    # Orden de migración básico: intenta orden por dependencias conocidas si existen
    # Si tus modelos usan FK tienes que ajustar el orden manualmente aquí
    preferred_order = []
    for n in ("User", "Product", "Sale", "SalesArchiveSummary"):
        if n in classes:
            preferred_order.append(classes[n])
    # añadir el resto que no estuvieran en preferred_order
    remaining = [c for name, c in classes.items() if c not in preferred_order]
    ordered = preferred_order + remaining

    summary = {}
    # Desactivar FK checks
    with engine_dst.connect() as conn_dst:
        try:
            conn_dst.execute(text("SET FOREIGN_KEY_CHECKS=0;"))
        except Exception as e:
            print("Advertencia: no se pudo desactivar FOREIGN_KEY_CHECKS:", e)

    for cls in ordered:
        name = cls.__name__
        print(f"\nMigrando modelo: {name}")
        try:
            with Session(engine_src) as s_src:
                rows = s_src.exec(select(cls)).all()
        except Exception as e:
            print(f"  ERROR leyendo {name} desde SQLite:", e)
            summary[name] = {"status": "read_error", "count": 0}
            continue

        total = len(rows)
        print(f"  Filas en SQLite: {total}")
        if total == 0:
            summary[name] = {"status": "empty", "count": 0}
            continue

        migrated = 0
        try:
            with Session(engine_dst) as s_dst:
                for r in rows:
                    # crear dict limpio
                    try:
                        data = r.dict(exclude_unset=False, by_alias=False)
                    except Exception:
                        data = {k: getattr(r, k) for k in vars(r) if not k.startswith("_")}
                    obj = cls(**data)
                    s_dst.add(obj)
                    migrated += 1
                s_dst.commit()
            summary[name] = {"status": "ok", "count": migrated}
            print(f"  Migradas: {migrated}/{total}")
        except Exception as e:
            print(f"  ERROR insertando {name} en MySQL:", e)
            summary[name] = {"status": "insert_error", "count": 0}

    # Reactivar FK checks
    with engine_dst.connect() as conn_dst:
        try:
            conn_dst.execute(text("SET FOREIGN_KEY_CHECKS=1;"))
        except Exception as e:
            print("Advertencia: no se pudo reactivar FOREIGN_KEY_CHECKS:", e)

    print("\nResumen (modelos):")
    for k, v in summary.items():
        print(f" - {k}: {v['status']} ({v['count']} filas)")
    return True

def migrate_by_reflect():
    print("Migración por REFLECT: leyendo tablas desde SQLite y copiando a MySQL")
    src_md = MetaData()
    try:
        src_md.reflect(bind=engine_src)
    except Exception as e:
        print("ERROR reflectando SQLite:", e)
        return False

    if not src_md.tables:
        print("No se detectaron tablas en dev.db. Revisa la ruta:", SQLITE_PATH)
        return False

    # Ver tablas detectadas
    tables = src_md.sorted_tables
    print("Tablas detectadas en SQLite (orden):", [t.name for t in tables])

    summary = {}
    with engine_dst.connect() as conn_dst:
        try:
            conn_dst.execute(text("SET FOREIGN_KEY_CHECKS=0;"))
        except Exception as e:
            print("Advertencia: no se pudo desactivar FOREIGN_KEY_CHECKS:", e)

        for table in tables:
            tname = table.name
            print(f"\nMigrando tabla: {tname}")
            try:
                with engine_src.connect() as conn_src:
                    rows = conn_src.execute(select(table)).mappings().all()
            except Exception as e:
                print("  ERROR leyendo desde SQLite:", e)
                summary[tname] = {"status": "read_error", "count": 0}
                continue

            count = len(rows)
            print(f"  Filas a migrar: {count}")
            if count == 0:
                summary[tname] = {"status": "empty", "count": 0}
                continue

            # Verificar tabla destino existe
            try:
                dst_table = Table(tname, MetaData(), autoload_with=engine_dst)
            except Exception as e:
                print(f"  ERROR: la tabla '{tname}' no existe en MySQL. Crea el esquema primero (create_schema_mysql.py) o revisa nombres:", e)
                summary[tname] = {"status": "missing_in_dest", "count": 0}
                continue

            # Insertar filas
            try:
                with engine_dst.begin() as trans:
                    trans.execute(dst_table.insert(), rows)
                summary[tname] = {"status": "ok", "count": count}
                print(f"  Insertadas: {count}")
            except SQLAlchemyError as e:
                print(f"  ERROR al insertar en MySQL: {e}")
                summary[tname] = {"status": "insert_error", "count": 0}

        try:
            conn_dst.execute(text("SET FOREIGN_KEY_CHECKS=1;"))
        except Exception as e:
            print("Advertencia: no se pudo reactivar FOREIGN_KEY_CHECKS:", e)

    print("\nResumen (reflect):")
    for k, v in summary.items():
        print(f" - {k}: {v['status']} ({v['count']} filas)")
    return True

def main():
    if not os.path.exists(SQLITE_PATH):
        print("ERROR: dev.db no encontrado en:", SQLITE_PATH)
        sys.exit(1)

    print("Se detectó dev.db. Asegúrate de tener un backup antes de continuar.")

    classes = try_import_models()
    if classes:
        ok = migrate_using_models(classes)
        if ok:
            print("\nMigración finalizada usando modelos.")
            return
        else:
            print("\nFallo migración usando modelos — intentando reflect fallback...")

    # Fallback: reflect and copy table-by-table
    ok2 = migrate_by_reflect()
    if ok2:
        print("\nMigración finalizada por reflect.")
    else:
        print("\nLa migración falló. Revisa mensajes anteriores.")

if __name__ == "__main__":
    main()