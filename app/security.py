from datetime import datetime, timedelta
import os
import logging
from typing import Optional, List

from passlib.context import CryptContext
from jose import jwt, JWTError

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.database import get_session
from app.models import User

logger = logging.getLogger("mini-pos.security")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Mapeo simple para aceptar etiquetas visuales (es) como alias de las claves internas
ROLE_ALIAS_MAP = {
    "ventas": "employee",
    "inventario": "stock",
    "administrador": "admin",
    # mantener mapeo directo por si el valor ya es la key
    "employee": "employee",
    "stock": "stock",
    "admin": "admin",
}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _raise_unauthorized(detail: str = "Could not validate credentials"):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def decode_token_or_401(token: str) -> dict:
    payload = decode_access_token(token)
    if not payload:
        _raise_unauthorized("Invalid or expired token")
    return payload


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)) -> User:
    payload = decode_token_or_401(token)
    username = payload.get("sub")
    if not username:
        _raise_unauthorized("Invalid token payload")
    user = db.exec(select(User).where(User.username == username)).first()
    if not user:
        _raise_unauthorized("User not found")
    return user


def require_role(allowed: List[str]):
    """
    Dependency: use as Depends(require_role(["admin","stock","employee"]))
    Compara case-insensitive y acepta alias (Ventas -> employee).
    """
    allowed_norm = {str(r).strip().lower() for r in (allowed or [])}

    def _require(user: User = Depends(get_current_user)) -> User:
        raw_role = str(getattr(user, "role", "") or "").strip().lower()
        canonical = ROLE_ALIAS_MAP.get(raw_role, raw_role)
        role_variants = {raw_role, canonical}
        if not (role_variants & allowed_norm):
            logger.debug(
                "require_role denied: raw_role=%r canonical=%r allowed=%r user_id=%s username=%s",
                raw_role,
                canonical,
                sorted(list(allowed_norm)),
                getattr(user, "id", None),
                getattr(user, "username", None),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _require