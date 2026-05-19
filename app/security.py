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


def setor_id_logado():
    try:
        return int(session.get("setor_id"))
    except (TypeError, ValueError):
        return None


def usuario_pode_acionar_tarefa(tarefa):
    if not is_setor():
        return True

    return setor_id_logado() == tarefa.setor_id


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


def mail_env(chave_mail, chave_smtp):
    return os.environ.get(chave_mail) or os.environ.get(chave_smtp)


def mail_usa_tls():
    valor = os.environ.get("MAIL_USE_TLS")
    if valor is None:
        return True
    return valor.strip().lower() in {"1", "true", "yes", "on"}


def smtp_configurado():
    return all([
        mail_env("MAIL_SERVER", "SMTP_HOST"),
        mail_env("MAIL_PORT", "SMTP_PORT"),
        mail_env("MAIL_USERNAME", "SMTP_USER"),
        mail_env("MAIL_PASSWORD", "SMTP_PASSWORD"),
        mail_env("MAIL_DEFAULT_SENDER", "SMTP_FROM")
    ])


def enviar_email_recuperacao(destinatario, codigo):
    if not smtp_configurado():
        # Fallback apenas para desenvolvimento local. Em producao, configure SMTP.
        print(f"[DEV] Codigo de recuperacao para {destinatario}: {codigo}")
        return

    mensagem = EmailMessage()
    mensagem["Subject"] = "Redefinicao de senha - Sistema OP"
    mensagem["From"] = mail_env("MAIL_DEFAULT_SENDER", "SMTP_FROM")
    mensagem["To"] = destinatario
    mensagem.set_content(
        "Use o codigo abaixo para redefinir sua senha. "
        "Ele expira em 10 minutos.\n\n"
        f"Codigo: {codigo}\n\n"
        "Se voce nao solicitou esta alteracao, ignore este email."
    )

    porta = int(mail_env("MAIL_PORT", "SMTP_PORT") or "587")
    try:
        with smtplib.SMTP(mail_env("MAIL_SERVER", "SMTP_HOST"), porta) as servidor:
            if mail_usa_tls():
                servidor.starttls()
            servidor.login(
                mail_env("MAIL_USERNAME", "SMTP_USER"),
                mail_env("MAIL_PASSWORD", "SMTP_PASSWORD")
            )
            servidor.send_message(mensagem)
    except Exception as erro:
        print(f"[ERRO] Falha ao enviar email de recuperacao: {erro}")
