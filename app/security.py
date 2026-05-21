from functools import wraps
import secrets

from flask import redirect, session, url_for

from email_service import enviar_email


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


def enviar_email_recuperacao(destinatario, codigo):
    resultado = enviar_email(
        [destinatario],
        "Redefinicao de senha - Sistema OP",
        "Use o codigo abaixo para redefinir sua senha. "
        "Ele expira em 10 minutos.\n\n"
        f"Codigo: {codigo}\n\n"
        "Se voce nao solicitou esta alteracao, ignore este email.",
    )
    return resultado.enviado
