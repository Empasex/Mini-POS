Mini POS - Backend (FastAPI + SQLModel + MySQL)

Pasos rápidos:
1. Copiar .env.example a .env y ajustar si hace falta.
2. Levantar con Docker:
   docker-compose up --build

O sin Docker:
1. python -m venv .venv
2. .venv\Scripts\activate (Windows) o source .venv/bin/activate (Unix)
3. pip install -r requirements.txt
4. export DATABASE_URL="mysql+pymysql://root:rootpwd@localhost:3306/minipos"
5. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

API (base: http://localhost:8000/api)
- GET /products
  - Lista todos los productos.
- GET /products/{id}
  - Obtiene producto por id.
- POST /products
  - Crea producto. Body: { "nombre": str, "descripcion": str?, "precio": float, "stock": int }
- PUT /products/{id}
  - Actualiza producto (reemplaza). Body igual al POST.
- DELETE /products/{id}
  - Elimina producto.

- GET /sales
  - Lista ventas. Query opcional: date_from (ISO), date_to (ISO)
- POST /sales
  - Crea venta y decrementa stock en la misma transacción.
  - Body: { "producto_id": int, "cantidad": int }
  - Respuestas:
    - 201: { sale data }
    - 400: si stock insuficiente o producto no existe

Docs OpenAPI: http://localhost:8000/docs
