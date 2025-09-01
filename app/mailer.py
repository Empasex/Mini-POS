import os
import logging
from typing import Dict, Any
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

logger = logging.getLogger("mini-pos.mailer")
logger.setLevel(logging.INFO)

MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Mini POS")

MAIL_STARTTLS = os.getenv("MAIL_TLS", "true").lower() in ("1", "true", "yes")
MAIL_SSL_TLS = os.getenv("MAIL_SSL", "false").lower() in ("1", "true", "yes")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    MAIL_PORT=MAIL_PORT,
    MAIL_SERVER=MAIL_SERVER or "localhost",
    MAIL_STARTTLS=MAIL_STARTTLS,
    MAIL_SSL_TLS=MAIL_SSL_TLS,
    USE_CREDENTIALS=bool(MAIL_USERNAME and MAIL_PASSWORD),
    VALIDATE_CERTS=True,
)


async def send_password_reset(recipient_email: str, token: str) -> Dict[str, Any]:
    reset_link = f"{FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    subject = "Restablecer contraseña - Mini POS"
    html = f"""
    <div>
      <p>Has solicitado restablecer tu contraseña.</p>
      <p>Haz clic en el siguiente enlace para restablecerla (expira en 1 hora):</p>
      <p><a href="{reset_link}">Restablecer contraseña</a></p>
      <p>Si no solicitaste el cambio, ignora este correo.</p>
    </div>
    """

    message = MessageSchema(
        subject=subject,
        recipients=[recipient_email],
        body=html,
        subtype=MessageType.html,
    )

    # if mail settings are missing, don't crash — return debug link and log
    if not MAIL_SERVER or not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.warning(
            "Mail not configured (MAIL_SERVER/MAIL_USERNAME/MAIL_PASSWORD). Returning debug link for %s: %s",
            recipient_email,
            reset_link,
        )
        return {"status": "not_configured", "to": recipient_email, "link": reset_link}

    try:
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info("Password reset email sent to %s", recipient_email)
        return {"status": "sent", "to": recipient_email, "link": reset_link}
    except Exception as e:
        logger.exception("Failed sending password reset to %s: %s", recipient_email, e)
        return {"status": "failed", "to": recipient_email, "error": str(e), "link": reset_link}


async def send_verification_email(recipient_email: str, token: str) -> Dict[str, Any]:
    verify_link = f"{FRONTEND_URL.rstrip('/')}/verify-recovery?token={token}"
    subject = "Verifica tu email de recuperación - Mini POS"
    html = f"""
    <div>
      <p>Gracias por configurar tu email de recuperación.</p>
      <p>Haz clic en el siguiente enlace para verificar tu email (expira en 24 horas):</p>
      <p><a href="{verify_link}">Verificar email</a></p>
      <p>Si no solicitaste esto, ignora este correo.</p>
    </div>
    """

    message = MessageSchema(
        subject=subject,
        recipients=[recipient_email],
        body=html,
        subtype=MessageType.html,
    )

    if not MAIL_SERVER or not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.warning(
            "Mail not configured (MAIL_SERVER/MAIL_USERNAME/MAIL_PASSWORD). Returning debug link for %s: %s",
            recipient_email,
            verify_link,
        )
        return {"status": "not_configured", "to": recipient_email, "link": verify_link}

    try:
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info("Verification email sent to %s", recipient_email)
        return {"status": "sent", "to": recipient_email, "link": verify_link}
    except Exception as e:
        logger.exception("Failed sending verification email to %s: %s", recipient_email, e)
        return {"status": "failed", "to": recipient_email, "error": str(e), "link": verify_link}