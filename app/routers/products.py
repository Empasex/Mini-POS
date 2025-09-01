from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from sqlmodel import select, Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session
from app.models import Product
from app.security import require_role

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=List[Product])
def list_products(session: Session = Depends(get_session)):
    try:
        return session.exec(select(Product)).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: int, session: Session = Depends(get_session)):
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return product
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.post("/", response_model=Product, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role(["admin", "stock"]))])
def create_product(product: Product, session: Session = Depends(get_session)):
    try:
        session.add(product)
        session.commit()
        session.refresh(product)
        return product
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.put("/{product_id}", response_model=Product, dependencies=[Depends(require_role(["admin", "stock"]))])
def update_product(product_id: int, product_in: Product, session: Session = Depends(get_session)):
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        product.nombre = product_in.nombre
        product.precio_venta = product_in.precio_venta
        product.costo_unitario = product_in.costo_unitario
        product.stock = product_in.stock
        session.add(product)
        session.commit()
        session.refresh(product)
        return product
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(["admin", "stock"]))])
def delete_product(product_id: int, session: Session = Depends(get_session)):
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        session.delete(product)
        session.commit()
        return None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from sqlmodel import select, Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session
from app.models import Product
from app.security import require_role

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=List[Product])
def list_products(session: Session = Depends(get_session)):
    try:
        return session.exec(select(Product)).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: int, session: Session = Depends(get_session)):
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return product
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.post("/", response_model=Product, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role(["admin", "stock"]))])
def create_product(product: Product, session: Session = Depends(get_session)):
    try:
        session.add(product)
        session.commit()
        session.refresh(product)
        return product
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.put("/{product_id}", response_model=Product, dependencies=[Depends(require_role(["admin", "stock"]))])
def update_product(product_id: int, product_in: Product, session: Session = Depends(get_session)):
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        product.nombre = product_in.nombre
        product.precio_venta = product_in.precio_venta
        product.costo_unitario = product_in.costo_unitario
        product.stock = product_in.stock
        session.add(product)
        session.commit()
        session.refresh(product)
        return product
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(["admin", "stock"]))])
def delete_product(product_id: int, session: Session = Depends(get_session)):
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        session.delete(product)
        session.commit()
        return None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")