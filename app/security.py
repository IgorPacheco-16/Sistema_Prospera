from functools import wraps
import secrets

from flask import redirect, session, url_for

from database.models import OPSetor, User
from email_service import enviar_codigo_cadastro, enviar_codigo_recuperacao

STATUS_OP_ENCERRADA = {"FINALIZADA", "ARQUIVADA"}


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


def usuario_pode_acionar_tarefa_por_setor(tarefa, tipo):
    setor_id = setor_id_logado()
    if setor_id is not None:
        if setor_id != tarefa.setor_id:
            return False
        return OPSetor.query.filter_by(
            op_id=tarefa.op_id,
            setor_id=setor_id,
        ).first() is not None

    setores_padrao = {
        "PCP": "pcp",
        "ATENDENTE": "atendimento",
    }

    setor_padrao = setores_padrao.get(tipo)
    if setor_padrao:
        return nome_setor_tarefa(tarefa) == setor_padrao

    return False


def usuario_pode_acionar_tarefa(tarefa):
    tipo = session.get("tipo")

    if tipo == "ADMIN":
        return True

    if tipo == "ESPECTADOR":
        return False

    if tipo == "SETOR":
        return usuario_pode_acionar_tarefa_por_setor(tarefa, tipo)

    responsaveis = list(getattr(tarefa, "responsaveis", []) or [])
    if responsaveis:
        usuario = usuario_logado_ativo()
        if usuario and any(responsavel.id == usuario.id for responsavel in responsaveis):
            return True

        if tipo in {"PCP", "ATENDENTE"}:
            return usuario_pode_acionar_tarefa_por_setor(tarefa, tipo)

        return False

    return usuario_pode_acionar_tarefa_por_setor(tarefa, tipo)


def usuario_pode_validar_tarefa(tarefa):
    tipo = session.get("tipo")
    return tipo in {"ADMIN", "ATENDENTE", "PCP"}


def usuario_pode_observar_tarefa(tarefa):
    tipo = session.get("tipo")

    if tipo in {"ADMIN", "PCP", "ATENDENTE"}:
        return True

    if tipo != "SETOR":
        return False

    setor_id = setor_id_logado()
    if setor_id is None or setor_id != tarefa.setor_id:
        return False

    return OPSetor.query.filter_by(
        op_id=tarefa.op_id,
        setor_id=setor_id,
    ).first() is not None


def op_esta_encerrada(op):
    return (
        not op
        or getattr(op, "status", None) in STATUS_OP_ENCERRADA
        or getattr(op, "finalizada_em", None) is not None
        or getattr(op, "arquivada_em", None) is not None
    )


def exigir_op_mutavel(op, mensagem="OP finalizada ou arquivada nao permite alteracoes"):
    if op_esta_encerrada(op):
        return mensagem, 400
    return None


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
    resultado = enviar_codigo_recuperacao(destinatario, codigo)
    return resultado.enviado


def enviar_email_cadastro(destinatario, codigo):
    resultado = enviar_codigo_cadastro(destinatario, codigo)
    return resultado.enviado
