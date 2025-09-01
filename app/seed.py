from sqlmodel import Session, select
from app.database import engine
from app.models import Product, Sale
from datetime import datetime, timedelta

MOCK_PRODUCTS = [
    {"nombre": "Gaseosa Cola 500ml", "precio_venta": 2.5, "costo_unitario": 1.2, "stock": 34},
    {"nombre": "Arroz 1kg", "precio_venta": 4.0, "costo_unitario": 2.5, "stock": 12},
    {"nombre": "Aceite 1L", "precio_venta": 7.5, "costo_unitario": 5.0, "stock": 6},
]


def seed():
    with Session(engine) as session:
        exists = session.exec(select(Product)).first()
        if exists:
            return
        for p in MOCK_PRODUCTS:
            session.add(Product(**p))
        # ventas de ejemplo
        session.add(Sale(producto_id=1, nombre="Gaseosa Cola 500ml", cantidad=2, total=5.0, hora=datetime.utcnow() - timedelta(days=1)))
        session.add(Sale(producto_id=2, nombre="Arroz 1kg", cantidad=1, total=4.0, hora=datetime.utcnow() - timedelta(days=2)))
        session.commit()


if __name__ == "__main__":
    seed()