...existing code...

# Mini-POS (WiseBiz Dashboard) — README adaptado

Mini-POS es un proyecto fullstack: frontend en React + TypeScript + Vite y backend en FastAPI (Python). Este README congrega la información práctica para desarrollar, probar y desplegar (Vercel frontend + Replit/Render backend), además de pasos Git para subir solo el frontend.

---

## Resúmen rápido
- Frontend: src/ (React + TS + Vite). Deploy estático en Vercel.
- Backend: backend/app (FastAPI). Actualmente en Replit en 
- DB: DB gestionada (Postgres/MySQL) para producción.

---

## Estructura relevante
- src/ — frontend (React + TS)
  - src/data/mock.ts (mocks)
  - src/lib/api.ts (axios wrapper)
  - src/pages/..., src/components/...
- backend/ — backend (FastAPI)
  - backend/app — routers, models, mailer, main.py
  - backend/start.sh, Dockerfile, docker-compose.yml

---

## Requisitos locales
- Node 18.x (recomendado)
- npm
- Python 3.10+
- pip, virtualenv (si no usas Docker)
- Docker (opcional)

---

## Variables de entorno (importantes)

Frontend (Vercel / .env.local)
- VITE_API_URL — URL base del backend (ej: https://<tu-repl>.spock.replit.dev). NO incluir `/api` al final.

Backend (Replit / Render / .env)
- DATABASE_URL — URL de la base de datos
- SECRET_KEY — clave para JWT
- ACCESS_TOKEN_EXPIRE_MINUTES
- MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_SERVER, MAIL_PORT, MAIL_TLS, MAIL_SSL
- FRONTEND_URL — URL del frontend para CORS (puede ser varias separadas por coma)
  - Ejemplo recomendado: `https://mini-pos-frontend.vercel.app,http://localhost:5173`

Nunca subir `.env` con credenciales al repo.

---

## Ejecutar en local

Frontend:
```bash
cd d:\mini-pos
npm ci
# Opcional: crear .env.local con VITE_API_URL
npm run dev
# Para build
npm run build
```

Backend (sin Docker):
```powershell
cd d:\mini-pos\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
# configurar env vars en Windows (ejemplo)
set DATABASE_URL=sqlite:///./dev.db
set SECRET_KEY=mi-secret
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend (Docker):
```bash
cd d:\mini-pos\backend
docker-compose up --build
```

Endpoints útiles:
- Backend docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

---

## Deploy — Frontend en Vercel (resumen)

1. Importa el repo (Empasex/Mini-POS-Frontend) en Vercel.
2. Root Directory: selecciona la carpeta donde está `package.json` (si está en la raíz, deja `.`).
3. Framework Preset: Vite
   - Install: npm ci
   - Build: npm run build
   - Output: dist
4. Environment Variables:
   - VITE_API_URL = https://<TU-BACKEND-REPL>.spock.replit.dev
5. Deploy. Copia la URL del deploy y añádela a `FRONTEND_URL` en el backend (Replit/Render) para CORS.

Forzar redeploy desde tu repo:
```bash
# commit vacío para forzar rebuild
git commit --allow-empty -m "Trigger Vercel rebuild"
git push frontend HEAD:main
```

---

## Deploy — Backend (Replit)

Replit (dev):
- Usa Replit Secrets (App Secrets) para DATABASE_URL, SECRET_KEY, MAIL_*, FRONTEND_URL.
---

## Conectar frontend + backend (CORS)

1. Vercel: VITE_API_URL apunta a backend.
2. Replit/Render: FRONTEND_URL contiene `https://mini-pos-frontend.vercel.app` (y `http://localhost:5173` para dev).



## Archivos de ejemplo (pegar si hacen falta)

package.json (frontend mínimo):
```json
{
  "name": "mini-pos-frontend",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.4.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "typescript": "^5.0.0",
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0"
  },
  "engines": { "node": "18.x" }
}
```

.env.example (backend)
```text
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=changeme
ACCESS_TOKEN_EXPIRE_MINUTES=60
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USERNAME=email@example.com
MAIL_PASSWORD=secret
MAIL_FROM=from@example.com
FRONTEND_URL=https://mini-pos-frontend.vercel.app
```

---
