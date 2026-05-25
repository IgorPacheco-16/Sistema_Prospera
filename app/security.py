from functools import wraps
import secrets

from flask import redirect, session, url_for

from database.models import User
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


def nome_setor_tarefa(tarefa):
    setor = getattr(tarefa, "setor", None)
    return (getattr(setor, "nome", "") or "").strip().lower()


def usuario_pode_acionar_tarefa(tarefa):
    tipo = session.get("tipo")

    if tipo == "ADMIN":
        return True

    if tipo == "ESPECTADOR":
        return False

    setor_id = setor_id_logado()
    if setor_id is not None:
        return setor_id == tarefa.setor_id

    setores_padrao = {
        "PCP": "pcp",
        "ATENDENTE": "atendimento",
    }

    setor_padrao = setores_padrao.get(tipo)
    if setor_padrao:
        return nome_setor_tarefa(tarefa) == setor_padrao

    return False


def usuario_logado_ativo():
    email = session.get("usuario")
    if not email:
        return None

    return User.query.filter_by(email=email, ativo=True).first()


def redirecionar_login_por_sessao_invalida():
    session.clear()
    return redirect(url_for("login"))


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not usuario_logado_ativo():
            return redirecionar_login_por_sessao_invalida()
        return func(*args, **kwargs)
    return wrapper


def tipos_permitidos(*tipos):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not usuario_logado_ativo():
                return redirecionar_login_por_sessao_invalida()

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


def enviar_email_cadastro(destinatario, codigo):
    resultado = enviar_email(
        [destinatario],
        "Codigo de verificacao - Sistema OP",
        "Use o codigo abaixo para continuar a criacao da sua conta. "
        "Ele expira em 15 minutos.\n\n"
        f"Codigo: {codigo}\n\n"
        "Se voce nao solicitou este cadastro, ignore este email.",
    )
    return resultado.enviado
