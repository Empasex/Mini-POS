from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select
import secrets

from app.database import get_session
from app.models import User
from app.security import get_password_hash, require_role

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_role(["admin"]))],
)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3)
    password: Optional[str] = Field(None, min_length=6)
    role: str = Field(..., min_length=3)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3)
    role: Optional[str] = Field(None, min_length=3)
    is_active: Optional[bool] = None
    # opcional: permitir establecer un email de recuperación si el modelo lo soporta
    recovery_email: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool = True


class UserCreatedOut(UserOut):
    temp_password: Optional[str] = None


def _to_out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, role=u.role, is_active=getattr(u, "is_active", True))


@router.get("/", response_model=List[UserOut])
def list_users(db: Session = Depends(get_session)):
    users = db.exec(select(User)).all()
    return [_to_out(u) for u in users]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_out(user)


@router.post("/", response_model=UserCreatedOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_session)):
    exists = db.exec(select(User).where(User.username == payload.username)).first()
    if exists:
        raise HTTPException(status_code=400, detail="Username already exists")
    # password provided or generate secure temporary
    if payload.password:
        pwd = payload.password
        temp = None
    else:
        pwd = secrets.token_urlsafe(10)
        temp = pwd
    user = User(username=payload.username, password_hash=get_password_hash(pwd), role=payload.role)
    # opcional: si tu modelo User soporta recovery_email, podrías inicializarlo aquí
    db.add(user)
    db.commit()
    db.refresh(user)
    out = _to_out(user)
    # return a Pydantic model instance (avoids mixing dicts in response)
    return UserCreatedOut(**out.dict(), temp_password=temp)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(require_role(["admin"])),
):
    """
    Update a user. Admins cannot deactivate their own account here.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from deactivating their own account
    if payload.is_active is not None and user_id == current_user.id:
        if payload.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    if payload.username:
        # check uniqueness
        exists = db.exec(select(User).where(User.username == payload.username, User.id != user_id)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username already in use")
        user.username = payload.username
    if payload.role:
        user.role = payload.role
    if payload.is_active is not None:
        setattr(user, "is_active", payload.is_active)
    # If payload includes recovery_email and model supports it, set it
    if payload.recovery_email is not None and hasattr(user, "recovery_email"):
        setattr(user, "recovery_email", payload.recovery_email)

    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    hard: bool = Query(False, description="If true, perform a hard delete. Default: false (soft-delete)"),
    db: Session = Depends(get_session),
    current_user: User = Depends(require_role(["admin"])),
):
    """
    Delete a user.
    - By default performs a soft-delete (sets is_active = False) if the model supports it.
    - If ?hard=true is provided, performs a hard delete (db.delete).
    - Admins cannot delete their own account (neither soft nor hard).
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if hard:
        # hard delete
        db.delete(user)
    else:
        # prefer soft-delete by is_active if model supports it; otherwise delete
        if hasattr(user, "is_active"):
            user.is_active = False
            db.add(user)
        else:
            db.delete(user)
    db.commit()
    return None


@router.post("/{user_id}/reset", response_model=dict)
def reset_password(user_id: int, db: Session = Depends(get_session)):
    """
    Generate a secure temporary password, set it for the user and return it once.
    Admin should communicate it securely to the user and recommend changing it on first login.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    temp = secrets.token_urlsafe(10)
    user.password_hash = get_password_hash(temp)
    db.add(user)
    db.commit()
    # return the temp password (show once). In production prefer sending by email instead.
    return {"msg": "Password reset", "temp_password": temp}