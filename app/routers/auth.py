from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Dict
from sqlmodel import Session, select
from datetime import datetime, timedelta
import secrets
import os

from app.database import get_session
from app.models import User
from app.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
)
from app.mailer import send_password_reset, send_verification_email

router = APIRouter(tags=["auth"])
api_sub = APIRouter(prefix="/api/auth", tags=["auth"])
public_sub = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "employee"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class RecoveryEmailIn(BaseModel):
    email: EmailStr


class RequestResetIn(BaseModel):
    email: EmailStr


class PerformResetIn(BaseModel):
    token: str
    new_password: str


class UsernameIn(BaseModel):
    username: str


def _login_impl(payload: LoginIn, db: Session):
    user = db.exec(select(User).where(User.username == payload.username)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "username": user.username, "role": user.role}


def _create_user_impl(payload: CreateUserIn, db: Session):
    exists = db.exec(select(User).where(User.username == payload.username)).first()
    if exists:
        raise HTTPException(status_code=400, detail="username exists")
    hashed = get_password_hash(payload.password)
    user = User(username=payload.username, password_hash=hashed, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"username": user.username, "role": user.role}


def _change_password_impl(payload: ChangePasswordIn, user: User, db: Session):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")
    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "Contraseña actualizada"}


def _me_impl(current_user: User):
    out: Dict = {
        "id": current_user.id,
        "username": current_user.username,
        "role": getattr(current_user, "role", None),
        "is_active": getattr(current_user, "is_active", True),
        "recovery_email": getattr(current_user, "recovery_email", None),
        "recovery_verified": getattr(current_user, "recovery_verified", False),
    }
    return out


def _set_recovery_email_impl(payload: RecoveryEmailIn, db: Session, current_user: User):
    if not hasattr(current_user, "recovery_email"):
        raise HTTPException(status_code=400, detail="Model does not have 'recovery_email' field. Add it to User model.")
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.recovery_email = payload.email
    user.recovery_verified = False
    token = secrets.token_urlsafe(24)
    expiry = datetime.utcnow() + timedelta(hours=24)
    user.recovery_verification_token = token
    user.recovery_verification_expires = expiry

    db.add(user)
    db.commit()
    db.refresh(user)

    # return the updated user and token so the caller can schedule the mail task
    return user, token


def _request_password_reset_impl(payload: RequestResetIn, db: Session):
    sample = db.exec(select(User)).first()
    if sample is None:
        raise HTTPException(status_code=404, detail="No users in DB")
    if not hasattr(sample, "recovery_email"):
        raise HTTPException(status_code=400, detail="Model does not have 'recovery_email' field. Add it to User model.")
    if not hasattr(sample, "reset_token") or not hasattr(sample, "reset_expires"):
        raise HTTPException(status_code=400, detail="Model must have 'reset_token' and 'reset_expires' fields to support password reset.")

    stmt = select(User).where(User.recovery_email == payload.email)
    user = db.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = secrets.token_urlsafe(24)
    expiry = datetime.utcnow() + timedelta(hours=1)
    user.reset_token = token
    user.reset_expires = expiry
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"msg": "Reset token generated", "token": token, "expires_at": expiry.isoformat()}


def _perform_password_reset_impl(payload: PerformResetIn, db: Session):
    sample = db.exec(select(User)).first()
    if sample is None:
        raise HTTPException(status_code=404, detail="No users in DB")
    if not hasattr(sample, "reset_token") or not hasattr(sample, "reset_expires"):
        raise HTTPException(status_code=400, detail="Model must have 'reset_token' and 'reset_expires' fields to support password reset.")

    now = datetime.utcnow()
    stmt = select(User).where(User.reset_token == payload.token)
    user = db.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    expires = getattr(user, "reset_expires", None)
    if not expires or expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")

    user.password_hash = get_password_hash(payload.new_password)
    user.reset_token = None
    user.reset_expires = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "Password updated successfully"}


@api_sub.post("/login", response_model=TokenOut)
@public_sub.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_session)):
    return _login_impl(payload, db)


@api_sub.post("/users", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
@public_sub.post("/users", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserIn, db: Session = Depends(get_session)):
    return _create_user_impl(payload, db)


@api_sub.post("/change-password")
@public_sub.post("/change-password")
def change_password(payload: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return _change_password_impl(payload, user, db)


@api_sub.get("/me", response_model=Dict)
@public_sub.get("/me", response_model=Dict)
def me(current_user: User = Depends(get_current_user)):
    return _me_impl(current_user)


@api_sub.post("/set_recovery_email", response_model=Dict)
@public_sub.post("/set_recovery_email", response_model=Dict)
async def set_recovery_email(
    payload: RecoveryEmailIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    user, token = _set_recovery_email_impl(payload, db, current_user)

    # schedule async mailer correctly via BackgroundTasks
    # BackgroundTasks will call the function/coroutine after response is sent
    background_tasks.add_task(send_verification_email, user.recovery_email, token)

    verify_link = f"{os.getenv('FRONTEND_URL','http://localhost:5173').rstrip('/')}/verify-recovery?token={token}"
    return {"msg": "Verification email scheduled", "debug_link": verify_link}


class VerifyTokenIn(BaseModel):
    token: str


@api_sub.post("/verify_recovery_email", response_model=Dict)
@public_sub.post("/verify_recovery_email", response_model=Dict)
def verify_recovery_email(payload: VerifyTokenIn, db: Session = Depends(get_session)):
    token = payload.token
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")
    now = datetime.utcnow()
    stmt = select(User).where(User.recovery_verification_token == token)
    user = db.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    expires = getattr(user, "recovery_verification_expires", None)
    if not expires or expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.recovery_verified = True
    user.recovery_verification_token = None
    user.recovery_verification_expires = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "Email verified"}


@api_sub.post("/request_password_reset", response_model=Dict)
@public_sub.post("/request_password_reset", response_model=Dict)
async def request_password_reset(payload: RequestResetIn, db: Session = Depends(get_session)):
    result = _request_password_reset_impl(payload, db)
    token = result.get("token")
    stmt = select(User).where(User.recovery_email == payload.email)
    user = db.exec(stmt).first()
    try:
        await send_password_reset(user.recovery_email, token)
    except Exception as e:
        user.reset_token = None
        user.reset_expires = None
        db.add(user)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed sending email: {e}")
    return {"msg": "If the email exists, a reset link was sent."}


@api_sub.post("/request_password_reset_by_username", response_model=Dict)
@public_sub.post("/request_password_reset_by_username", response_model=Dict)
async def request_password_reset_by_username(
    payload: UsernameIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    """
    Request a password reset by username. If the user exists and has a recovery_email,
    generate a reset token, save it and schedule sending the reset email in background.

    Returns a generic message to avoid account enumeration.
    """
    username = (payload or {}).username
    if not username:
        raise HTTPException(status_code=400, detail="Missing username")

    stmt = select(User).where(User.username == username)
    user = db.exec(stmt).first()

    # Generic response for security
    generic = {"msg": "If the account exists and has a recovery email, a reset link will be sent."}

    if not user:
        return generic

    recovery_email = getattr(user, "recovery_email", None)
    if not recovery_email:
        return generic

    # create reset token & expiry (1 hour)
    token = secrets.token_urlsafe(24)
    expiry = datetime.utcnow() + timedelta(hours=1)
    user.reset_token = token
    user.reset_expires = expiry

    db.add(user)
    db.commit()
    db.refresh(user)

    # schedule background send (mailer.send_password_reset is async)
    background_tasks.add_task(send_password_reset, recovery_email, token)

    return generic


@api_sub.post("/perform_password_reset", response_model=Dict)
@public_sub.post("/perform_password_reset", response_model=Dict)
def perform_password_reset(payload: PerformResetIn, db: Session = Depends(get_session)):
    return _perform_password_reset_impl(payload, db)


router.include_router(api_sub)
router.include_router(public_sub)
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Dict
from sqlmodel import Session, select
from datetime import datetime, timedelta
import secrets
import os

from app.database import get_session
from app.models import User
from app.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
)
from app.mailer import send_password_reset, send_verification_email

router = APIRouter(tags=["auth"])
api_sub = APIRouter(prefix="/api/auth", tags=["auth"])
public_sub = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "employee"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class RecoveryEmailIn(BaseModel):
    email: EmailStr


class RequestResetIn(BaseModel):
    email: EmailStr


class PerformResetIn(BaseModel):
    token: str
    new_password: str


class UsernameIn(BaseModel):
    username: str


def _login_impl(payload: LoginIn, db: Session):
    user = db.exec(select(User).where(User.username == payload.username)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "username": user.username, "role": user.role}


def _create_user_impl(payload: CreateUserIn, db: Session):
    exists = db.exec(select(User).where(User.username == payload.username)).first()
    if exists:
        raise HTTPException(status_code=400, detail="username exists")
    hashed = get_password_hash(payload.password)
    user = User(username=payload.username, password_hash=hashed, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"username": user.username, "role": user.role}


def _change_password_impl(payload: ChangePasswordIn, user: User, db: Session):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")
    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "Contraseña actualizada"}


def _me_impl(current_user: User):
    out: Dict = {
        "id": current_user.id,
        "username": current_user.username,
        "role": getattr(current_user, "role", None),
        "is_active": getattr(current_user, "is_active", True),
        "recovery_email": getattr(current_user, "recovery_email", None),
        "recovery_verified": getattr(current_user, "recovery_verified", False),
    }
    return out


def _set_recovery_email_impl(payload: RecoveryEmailIn, db: Session, current_user: User):
    if not hasattr(current_user, "recovery_email"):
        raise HTTPException(status_code=400, detail="Model does not have 'recovery_email' field. Add it to User model.")
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.recovery_email = payload.email
    user.recovery_verified = False
    token = secrets.token_urlsafe(24)
    expiry = datetime.utcnow() + timedelta(hours=24)
    user.recovery_verification_token = token
    user.recovery_verification_expires = expiry

    db.add(user)
    db.commit()
    db.refresh(user)

    # return the updated user and token so the caller can schedule the mail task
    return user, token


def _request_password_reset_impl(payload: RequestResetIn, db: Session):
    sample = db.exec(select(User)).first()
    if sample is None:
        raise HTTPException(status_code=404, detail="No users in DB")
    if not hasattr(sample, "recovery_email"):
        raise HTTPException(status_code=400, detail="Model does not have 'recovery_email' field. Add it to User model.")
    if not hasattr(sample, "reset_token") or not hasattr(sample, "reset_expires"):
        raise HTTPException(status_code=400, detail="Model must have 'reset_token' and 'reset_expires' fields to support password reset.")

    stmt = select(User).where(User.recovery_email == payload.email)
    user = db.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = secrets.token_urlsafe(24)
    expiry = datetime.utcnow() + timedelta(hours=1)
    user.reset_token = token
    user.reset_expires = expiry
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"msg": "Reset token generated", "token": token, "expires_at": expiry.isoformat()}


def _perform_password_reset_impl(payload: PerformResetIn, db: Session):
    sample = db.exec(select(User)).first()
    if sample is None:
        raise HTTPException(status_code=404, detail="No users in DB")
    if not hasattr(sample, "reset_token") or not hasattr(sample, "reset_expires"):
        raise HTTPException(status_code=400, detail="Model must have 'reset_token' and 'reset_expires' fields to support password reset.")

    now = datetime.utcnow()
    stmt = select(User).where(User.reset_token == payload.token)
    user = db.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    expires = getattr(user, "reset_expires", None)
    if not expires or expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")

    user.password_hash = get_password_hash(payload.new_password)
    user.reset_token = None
    user.reset_expires = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "Password updated successfully"}


@api_sub.post("/login", response_model=TokenOut)
@public_sub.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_session)):
    return _login_impl(payload, db)


@api_sub.post("/users", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
@public_sub.post("/users", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserIn, db: Session = Depends(get_session)):
    return _create_user_impl(payload, db)


@api_sub.post("/change-password")
@public_sub.post("/change-password")
def change_password(payload: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    return _change_password_impl(payload, user, db)


@api_sub.get("/me", response_model=Dict)
@public_sub.get("/me", response_model=Dict)
def me(current_user: User = Depends(get_current_user)):
    return _me_impl(current_user)


@api_sub.post("/set_recovery_email", response_model=Dict)
@public_sub.post("/set_recovery_email", response_model=Dict)
async def set_recovery_email(
    payload: RecoveryEmailIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    user, token = _set_recovery_email_impl(payload, db, current_user)

    # schedule async mailer correctly via BackgroundTasks
    # BackgroundTasks will call the function/coroutine after response is sent
    background_tasks.add_task(send_verification_email, user.recovery_email, token)

    verify_link = f"{os.getenv('FRONTEND_URL','http://localhost:5173').rstrip('/')}/verify-recovery?token={token}"
    return {"msg": "Verification email scheduled", "debug_link": verify_link}


class VerifyTokenIn(BaseModel):
    token: str


@api_sub.post("/verify_recovery_email", response_model=Dict)
@public_sub.post("/verify_recovery_email", response_model=Dict)
def verify_recovery_email(payload: VerifyTokenIn, db: Session = Depends(get_session)):
    token = payload.token
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")
    now = datetime.utcnow()
    stmt = select(User).where(User.recovery_verification_token == token)
    user = db.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    expires = getattr(user, "recovery_verification_expires", None)
    if not expires or expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.recovery_verified = True
    user.recovery_verification_token = None
    user.recovery_verification_expires = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "Email verified"}


@api_sub.post("/request_password_reset", response_model=Dict)
@public_sub.post("/request_password_reset", response_model=Dict)
async def request_password_reset(payload: RequestResetIn, db: Session = Depends(get_session)):
    result = _request_password_reset_impl(payload, db)
    token = result.get("token")
    stmt = select(User).where(User.recovery_email == payload.email)
    user = db.exec(stmt).first()
    try:
        await send_password_reset(user.recovery_email, token)
    except Exception as e:
        user.reset_token = None
        user.reset_expires = None
        db.add(user)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed sending email: {e}")
    return {"msg": "If the email exists, a reset link was sent."}


@api_sub.post("/request_password_reset_by_username", response_model=Dict)
@public_sub.post("/request_password_reset_by_username", response_model=Dict)
async def request_password_reset_by_username(
    payload: UsernameIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    """
    Request a password reset by username. If the user exists and has a recovery_email,
    generate a reset token, save it and schedule sending the reset email in background.

    Returns a generic message to avoid account enumeration.
    """
    username = (payload or {}).username
    if not username:
        raise HTTPException(status_code=400, detail="Missing username")

    stmt = select(User).where(User.username == username)
    user = db.exec(stmt).first()

    # Generic response for security
    generic = {"msg": "If the account exists and has a recovery email, a reset link will be sent."}

    if not user:
        return generic

    recovery_email = getattr(user, "recovery_email", None)
    if not recovery_email:
        return generic

    # create reset token & expiry (1 hour)
    token = secrets.token_urlsafe(24)
    expiry = datetime.utcnow() + timedelta(hours=1)
    user.reset_token = token
    user.reset_expires = expiry

    db.add(user)
    db.commit()
    db.refresh(user)

    # schedule background send (mailer.send_password_reset is async)
    background_tasks.add_task(send_password_reset, recovery_email, token)

    return generic


@api_sub.post("/perform_password_reset", response_model=Dict)
@public_sub.post("/perform_password_reset", response_model=Dict)
def perform_password_reset(payload: PerformResetIn, db: Session = Depends(get_session)):
    return _perform_password_reset_impl(payload, db)


router.include_router(api_sub)
router.include_router(public_sub)