# ...existing code...
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str
    precio_venta: float
    costo_unitario: float = 0.0
    stock: int = 0
    created_at: Optional[datetime] = Field(default=None, nullable=True)
    updated_at: Optional[datetime] = Field(default=None, nullable=True)

class Sale(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    producto_id: int
    nombre: str
    cantidad: int
    total: float
    hora: datetime = Field(default_factory=datetime.utcnow)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, nullable=False)
    password_hash: str
    role: str = Field(default="employee")
    is_active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(default=None, nullable=True)

    # Campos nuevos para recuperación/verificación de email
    recovery_email: Optional[str] = Field(default=None, index=True, nullable=True)
    recovery_verified: bool = Field(default=False)
    recovery_verification_token: Optional[str] = Field(default=None, nullable=True)
    recovery_verification_expires: Optional[datetime] = Field(default=None, nullable=True)

    # Campos para reset de contraseña (opcional)
    reset_token: Optional[str] = Field(default=None, nullable=True)
    reset_expires: Optional[datetime] = Field(default=None, nullable=True)

class SalesArchiveSummary(SQLModel, table=True):
    """
    Resumen por batch de ventas.
    Clave primaria compuesta: (batch_id, producto_id)
    """
    batch_id: str = Field(primary_key=True, max_length=36)
    producto_id: int = Field(primary_key=True)
    nombre: Optional[str] = Field(default=None, nullable=True)
    cantidad_total: int = Field(default=0)
    ingresos: float = Field(default=0.0)
    costos: float = Field(default=0.0)
    ganancia: float = Field(default=0.0)
    min_hora: Optional[datetime] = Field(default=None, nullable=True)
    max_hora: Optional[datetime] = Field(default=None, nullable=True)
    created_at: Optional[datetime] = Field(default=None, nullable=True)
# ...existing code...