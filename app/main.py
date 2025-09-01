# ...existing code...
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlmodel import SQLModel
from app.database import engine
from app.routers import products, sales, archive, auth
from app.routers.admin_users import router as admin_users_router
from app import seed

from dotenv import load_dotenv
import os
import logging

logging.basicConfig(level=logging.INFO)
# carga backend/.env (ruta relativa)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

def _mask(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v)
    return s if len(s) <= 6 else f"{s[:3]}...{s[-3:]}"

logging.info("ENV check: FRONTEND_URL=%s MAIL_SERVER=%s MAIL_USERNAME=%s",
             os.getenv("FRONTEND_URL"),
             _mask(os.getenv("MAIL_SERVER")),
             _mask(os.getenv("MAIL_USERNAME")))

app = FastAPI(title="mini-pos API")

# Configurar CORS dinámicamente usando FRONTEND_URL (comma-separated)
frontend_env = os.getenv("FRONTEND_URL", "").strip()
if frontend_env:
    origins = [u.strip() for u in frontend_env.split(",") if u.strip()]
else:
    # En desarrollo mantenemos localhost para Vite; en producción define FRONTEND_URL en Replit
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(products.router)
app.include_router(sales.router)
# monta router de archive con prefijo /api -> rutas finales /api/archive/...
app.include_router(archive.router, prefix="/api")
# auth router (puede incluir su propio prefijo, por ejemplo /api/auth)
app.include_router(auth.router)
# admin users router (prefijo ya definido en admin_users.py)
app.include_router(admin_users_router)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    try:
        seed.seed()
    except Exception:
        pass
    # imprime rutas para verificar en consola
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = ",".join(sorted(route.methods))
            print(f"Route: {route.path}  methods: {methods}")
# ...existing code...