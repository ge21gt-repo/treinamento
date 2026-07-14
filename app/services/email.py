"""Servico de envio de e-mails (SMTP ou fallback para console)."""

import logging
import smtplib
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_reset_email(destino_email: str, nome_usuario: str, link_reset: str) -> bool:
    assunto = "Redefinicao de senha - LMS IDE-SP"
    corpo = f"""
Olá {nome_usuario},

Recebemos uma solicitacao de redefinicao de senha para sua conta.

Clique no link abaixo para redefinir sua senha:
{link_reset}

Este link expira em 1 hora.

Se voce nao solicitou esta redefinicao, ignore este e-mail.

Atenciosamente,
Equipe LMS IDE-SP
"""
    try:
        msg = MIMEText(corpo, "plain", "utf-8")
        msg["Subject"] = assunto
        msg["From"] = settings.SMTP_FROM
        msg["To"] = destino_email

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email de reset enviado para {destino_email}")
        return True
    except Exception as e:
        logger.warning(f"Falha ao enviar email para {destino_email}: {e}")
        logger.info(f"[DEV] Link de reset: {link_reset}")
        return False
