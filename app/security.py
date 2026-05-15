from email.message import EmailMessage
from functools import wraps
import os
import secrets
import smtplib

from flask import redirect, session, url_for


def is_admin():
    return session.get("tipo") == "ADMIN"


def is_atendente():
    return session.get("tipo") == "ATENDENTE"


def is_pcp():
    return session.get("tipo") == "PCP"


def is_setor():
    return session.get("tipo") == "SETOR"


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def tipos_permitidos(*tipos):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("login"))

            if session.get("tipo") not in tipos:
                return "Acesso negado", 403

            return func(*args, **kwargs)
        return wrapper
    return decorator


def normalizar_email(email):
    return (email or "").strip().lower()


def gerar_codigo_recuperacao():
    return f"{secrets.randbelow(1_000_000):06d}"


def smtp_configurado():
    return all([
        os.environ.get("SMTP_HOST"),
        os.environ.get("SMTP_PORT"),
        os.environ.get("SMTP_USER"),
        os.environ.get("SMTP_PASSWORD"),
        os.environ.get("SMTP_FROM")
    ])


def enviar_email_recuperacao(destinatario, codigo):
    if not smtp_configurado():
        # Fallback apenas para desenvolvimento local. Em producao, configure SMTP.
        print(f"[DEV] Codigo de recuperacao para {destinatario}: {codigo}")
        return

    mensagem = EmailMessage()
    mensagem["Subject"] = "Redefinicao de senha - Sistema OP"
    mensagem["From"] = os.environ["SMTP_FROM"]
    mensagem["To"] = destinatario
    mensagem.set_content(
        "Use o codigo abaixo para redefinir sua senha. "
        "Ele expira em 10 minutos.\n\n"
        f"Codigo: {codigo}\n\n"
        "Se voce nao solicitou esta alteracao, ignore este email."
    )

    porta = int(os.environ.get("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], porta) as servidor:
            servidor.starttls()
            servidor.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            servidor.send_message(mensagem)
    except Exception as erro:
        print(f"[ERRO] Falha ao enviar email de recuperacao: {erro}")
