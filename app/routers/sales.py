from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional
from sqlmodel import Session, select
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel

from app.database import get_session
from app.models import Sale, Product
from app.security import require_role

router = APIRouter(prefix="/api/sales", tags=["sales"])


class SaleCreate(BaseModel):
    producto_id: int
    cantidad: int


# Permitir tanto la clave interna 'employee' como la etiqueta 'ventas' (security lo maneja)
@router.get("/", response_model=List[Sale], dependencies=[Depends(require_role(["admin", "stock", "employee", "ventas"]))])
def list_sales(session: Session = Depends(get_session), start: Optional[str] = Query(None), end: Optional[str] = Query(None)):
    try:
        q = select(Sale)
        if start:
            q = q.where(Sale.hora >= datetime.fromisoformat(start))
        if end:
            q = q.where(Sale.hora <= datetime.fromisoformat(end))
        return session.exec(q).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.post(
    "/",
    response_model=Sale,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin", "stock", "employee", "ventas"]))],
)
def create_sale(sale_in: SaleCreate, session: Session = Depends(get_session)):
    try:
        prod = session.get(Product, sale_in.producto_id)
        if not prod:
            raise HTTPException(status_code=400, detail="Producto no existe")
        if prod.stock < sale_in.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente")
        prod.stock = prod.stock - sale_in.cantidad
        session.add(prod)
        total = round(prod.precio_venta * sale_in.cantidad, 2)
        sale = Sale(producto_id=sale_in.producto_id, nombre=prod.nombre, cantidad=sale_in.cantidad, total=total)
        session.add(sale)
        session.commit()
        session.refresh(sale)
        return sale
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")