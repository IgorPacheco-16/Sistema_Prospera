from datetime import date, timedelta
from email.message import EmailMessage
import os
import smtplib
import sys

from flask import current_app, has_request_context, request, session

from database.models import db, Notificacao, OP, OPSetor, Tarefa, User


EMAILS_OPERACIONAIS = {
    "op_criada": {
        "assunto": "Nova OP criada",
        "titulo": "Nova OP criada",
        "chamada": "Uma nova ordem de producao foi aberta para planejamento.",
    },
    "op_urgente": {
        "assunto": "OP URGENTE",
        "titulo": "OP urgente",
        "chamada": "Esta OP esta perto do prazo final.",
    },
    "op_atrasada": {
        "assunto": "OP ATRASADA",
        "titulo": "OP atrasada",
        "chamada": "Esta OP passou do prazo final e precisa de atencao.",
    },
    "tarefa_atrasada": {
        "assunto": "TAREFA ATRASADA",
        "titulo": "Tarefa atrasada",
        "chamada": "Uma tarefa passou do prazo e pode impactar a OP.",
    },
    "tarefa_aguardando_validacao": {
        "assunto": "VALIDACAO PENDENTE",
        "titulo": "Validacao pendente",
        "chamada": "Uma tarefa foi enviada para validacao.",
    },
}

ASSUNTO_PREFIXO = {
    "op_criada": "\U0001F195",
    "op_urgente": "\U0001F6A8",
    "op_atrasada": "\U0001F6A8",
    "tarefa_atrasada": "\u23F0",
    "tarefa_aguardando_validacao": "\u23F3",
}


def imprimir_log_email(texto):
    try:
        print(texto)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        texto_seguro = texto.encode(encoding, errors="replace").decode(encoding)
        print(texto_seguro)


def link_op(op_id):
    return f"/op/{op_id}"


def link_tarefa(op_id, setor_id, tarefa_id):
    return f"/op/{op_id}?setor={setor_id}&tarefa={tarefa_id}"


def smtp_configurado():
    return all([
        os.environ.get("SMTP_HOST"),
        os.environ.get("SMTP_PORT"),
        os.environ.get("SMTP_USER"),
        os.environ.get("SMTP_PASSWORD"),
        os.environ.get("SMTP_FROM")
    ])


def url_absoluta(link):
    if not link:
        return ""
    if link.startswith("http://") or link.startswith("https://"):
        return link

    base_url = os.environ.get("APP_BASE_URL", "").rstrip("/")
    if not base_url and has_request_context():
        base_url = request.host_url.rstrip("/")
    if not base_url:
        base_url = "http://localhost:5000"

    return f"{base_url}/{link.lstrip('/')}"


def formatar_data_email(valor):
    if not valor:
        return "Sem prazo"
    return valor.strftime("%d/%m/%Y")


def prioridade_op(op):
    return "Alta prioridade" if getattr(op, "alta_prioridade", False) else "Normal"


def emails_unicos(usuarios):
    emails = []
    for usuario in usuarios:
        email = (usuario.email or "").strip().lower()
        if email and email not in emails:
            emails.append(email)
    return emails


def destinatarios_por_tipo(tipo):
    query = User.query.filter_by(tipo=tipo, ativo=True)
    return emails_unicos(query.all())


def destinatarios_por_setor(setor_id):
    if not setor_id:
        return []

    query = User.query.filter_by(setor_id=setor_id, ativo=True)
    return emails_unicos(query.all())


def destinatarios_email_operacional(evento, op=None, tarefa=None):
    if evento == "op_criada":
        return destinatarios_por_tipo("PCP")

    if evento in ("op_urgente", "op_atrasada", "tarefa_aguardando_validacao"):
        return destinatarios_por_tipo("ATENDENTE") + destinatarios_por_tipo("PCP")

    if evento == "tarefa_atrasada":
        setor_id = tarefa.setor_id if tarefa else None
        return (
            destinatarios_por_setor(setor_id)
            + destinatarios_por_tipo("ATENDENTE")
            + destinatarios_por_tipo("PCP")
        )

    return []


def log_destinatarios_email(evento, emails, smtp_ativo):
    status = "SMTP ativo" if smtp_ativo else "SMTP ausente"
    destino = ", ".join(emails) if emails else "(nenhum)"
    imprimir_log_email(
        f"[EMAIL OPERACIONAL][DESTINATARIOS] {evento} | {status} -> {destino}"
    )


def enviar_email_operacional(
    evento,
    op=None,
    tarefa=None,
    link=None,
    destinatarios=None,
    notificacoes=None
):
    config = EMAILS_OPERACIONAIS.get(evento)
    if not config:
        return False

    notificacoes = notificacoes or []
    if notificacoes and not any(getattr(n, "_foi_criada", False) for n in notificacoes):
        return False

    emails = destinatarios or destinatarios_email_operacional(evento, op=op, tarefa=tarefa)
    emails = list(dict.fromkeys((email or "").strip().lower() for email in emails if email))

    smtp_ativo = smtp_configurado()
    log_destinatarios_email(evento, emails, smtp_ativo)

    if not emails:
        imprimir_log_email(f"[EMAIL OPERACIONAL] Sem destinatarios para {evento}.")
        return False

    link_final = url_absoluta(link or (link_tarefa(op.id, tarefa.setor_id, tarefa.id) if op and tarefa else link_op(op.id) if op else ""))
    assunto = f"{ASSUNTO_PREFIXO.get(evento, '[OP]')} {config['assunto']}"
    contexto = {
        "evento": evento,
        "titulo": config["titulo"],
        "chamada": config["chamada"],
        "op": op,
        "tarefa": tarefa,
        "prazo": formatar_data_email(tarefa.prazo if tarefa else op.prazo_final if op else None),
        "prioridade": prioridade_op(op) if op else "-",
        "link": link_final,
    }
    html = current_app.jinja_env.get_template("email/operacional.html").render(**contexto)
    texto = (
        f"{config['titulo']}\n\n"
        f"OP: {op.nome if op else '-'}\n"
        f"Tarefa: {tarefa.nome if tarefa else '-'}\n"
        f"Prazo: {contexto['prazo']}\n"
        f"Prioridade: {contexto['prioridade']}\n"
        f"Link: {link_final}\n"
    )

    if not smtp_ativo:
        imprimir_log_email(
            f"[EMAIL OPERACIONAL][DEV] {assunto} -> {', '.join(emails)}\n{texto}"
        )
        return False

    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = os.environ["SMTP_FROM"]
    mensagem["To"] = ", ".join(emails)
    mensagem.set_content(texto)
    mensagem.add_alternative(html, subtype="html")

    porta = int(os.environ.get("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], porta) as servidor:
            servidor.starttls()
            servidor.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            servidor.send_message(mensagem)
        return True
    except Exception as erro:
        imprimir_log_email(f"[ERRO] Falha ao enviar email operacional ({evento}): {erro}")
        return False


def query_notificacoes_usuario():
    query = Notificacao.query.filter_by(usuario=session.get("tipo"))

    if session.get("tipo") == "SETOR":
        query = query.filter_by(setor_id=session.get("setor_id"))

    return query


def setores_da_op(op_id):
    return OPSetor.query.filter_by(op_id=op_id).all()


def mensagem_op(evento, op):
    titulos = {
        "op_atrasada": "🚨 URGENTE • OP ATRASADA",
        "op_criada": "🆕 NOVA OP",
        "op_finalizada": "🎉 OP FINALIZADA",
        "op_urgente": "⚠️ PRIORIDADE ALTA",
    }
    titulo = titulos.get(evento, "ℹ️ OP")
    return f"{titulo}\nOP: {op.nome}"


def mensagem_tarefa(evento, op, tarefa):
    titulos = {
        "tarefa_atrasada": "🚨 URGENTE • TAREFA ATRASADA",
        "tarefa_em_andamento": "▶️ TAREFA EM ANDAMENTO",
        "tarefa_aguardando_validacao": "⏳ VALIDAÇÃO PENDENTE",
        "tarefa_criada": "🆕 NOVA TAREFA",
        "entrega_validada": "✅ ENTREGA VALIDADA",
        "entrega_recusada": "❌ ENTREGA RECUSADA",
    }
    titulo = titulos.get(evento, "ℹ️ TAREFA")
    return f"{titulo}\nOP: {op.nome}\nTarefa: {tarefa.nome}"


def categoria_notificacao(tipo_evento):
    if tipo_evento in ("op_atrasada", "tarefa_atrasada", "op_urgente"):
        return "urgente"
    if tipo_evento == "tarefa_aguardando_validacao":
        return "pendente"
    if tipo_evento in ("entrega_validada", "op_finalizada"):
        return "sucesso"
    return "info"


def criar_notificacao(
    usuario,
    mensagem,
    link=None,
    op_id=None,
    tarefa_id=None,
    setor_id=None,
    tipo_evento=None
):
    if tipo_evento:
        existe = Notificacao.query.filter_by(
            usuario=usuario,
            op_id=op_id,
            tarefa_id=tarefa_id,
            setor_id=setor_id,
            tipo_evento=tipo_evento
        ).first()
    else:
        existe = Notificacao.query.filter_by(
            usuario=usuario,
            mensagem=mensagem
        ).first()

    if existe:
        existe._foi_criada = False
        return existe

    notificacao = Notificacao(
        usuario=usuario,
        mensagem=mensagem,
        link=link,
        op_id=op_id,
        tarefa_id=tarefa_id,
        setor_id=setor_id,
        tipo_evento=tipo_evento
    )

    db.session.add(notificacao)
    notificacao._foi_criada = True
    return notificacao


def notificar_op_para_gestao(op, tipo_evento, mensagem):
    notificacoes = []
    notificacoes.append(criar_notificacao(
        "ATENDENTE",
        mensagem,
        link=link_op(op.id),
        op_id=op.id,
        tipo_evento=tipo_evento
    ))
    notificacoes.append(criar_notificacao(
        "PCP",
        mensagem,
        link=link_op(op.id),
        op_id=op.id,
        tipo_evento=tipo_evento
    ))
    return notificacoes


def notificar_op_para_setores(op, tipo_evento, mensagem):
    notificacoes = []
    for op_setor in setores_da_op(op.id):
        notificacoes.append(criar_notificacao(
            "SETOR",
            mensagem,
            link=f"/op/{op.id}?setor={op_setor.setor_id}",
            op_id=op.id,
            setor_id=op_setor.setor_id,
            tipo_evento=tipo_evento
        ))
    return notificacoes


def verificar_atrasos():
    hoje = date.today()
    tarefas = Tarefa.query.filter(
        Tarefa.prazo < hoje,
        Tarefa.validado == False
    ).all()

    for t in tarefas:
        op = db.session.get(OP, t.op_id)
        if not op:
            continue

        mensagem = mensagem_tarefa("tarefa_atrasada", op, t)
        link = link_tarefa(op.id, t.setor_id, t.id)
        notificacoes = []

        for usuario in ["ATENDENTE", "PCP"]:
            notificacoes.append(criar_notificacao(
                usuario,
                mensagem,
                link=link,
                op_id=op.id,
                tarefa_id=t.id,
                setor_id=t.setor_id,
                tipo_evento="tarefa_atrasada"
            ))

        notificacoes.append(criar_notificacao(
            "SETOR",
            mensagem,
            link=link,
            op_id=op.id,
            tarefa_id=t.id,
            setor_id=t.setor_id,
            tipo_evento="tarefa_atrasada"
        ))
        enviar_email_operacional(
            "tarefa_atrasada",
            op=op,
            tarefa=t,
            link=link,
            notificacoes=notificacoes
        )

    ops_atrasadas = OP.query.filter(
        OP.prazo_final < hoje,
        OP.status.notin_(["FINALIZADA", "ARQUIVADA"])
    ).all()

    for op in ops_atrasadas:
        mensagem = mensagem_op("op_atrasada", op)
        notificacoes = notificar_op_para_gestao(op, "op_atrasada", mensagem)
        notificar_op_para_setores(op, "op_atrasada", mensagem)
        enviar_email_operacional(
            "op_atrasada",
            op=op,
            link=link_op(op.id),
            notificacoes=notificacoes
        )

    ops_urgentes = OP.query.filter(
        OP.prazo_final >= hoje,
        OP.prazo_final <= hoje + timedelta(days=2),
        OP.status.notin_(["FINALIZADA", "ARQUIVADA"])
    ).all()

    for op in ops_urgentes:
        mensagem = mensagem_op("op_urgente", op)
        notificacoes = notificar_op_para_gestao(op, "op_urgente", mensagem)
        notificar_op_para_setores(op, "op_urgente", mensagem)
        enviar_email_operacional(
            "op_urgente",
            op=op,
            link=link_op(op.id),
            notificacoes=notificacoes
        )


def gerar_notificacoes_pendentes():
    verificar_atrasos()

    tarefas_entregues = Tarefa.query.filter_by(
        entregue=True,
        validado=False
    ).all()

    for tarefa in tarefas_entregues:
        op = db.session.get(OP, tarefa.op_id)
        if not op:
            continue

        mensagem = mensagem_tarefa("tarefa_aguardando_validacao", op, tarefa)
        link = link_tarefa(op.id, tarefa.setor_id, tarefa.id)
        notificacoes = []

        for usuario in ["ATENDENTE", "PCP"]:
            notificacoes.append(criar_notificacao(
                usuario,
                mensagem,
                link=link,
                op_id=op.id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento="tarefa_aguardando_validacao"
            ))
        enviar_email_operacional(
            "tarefa_aguardando_validacao",
            op=op,
            tarefa=tarefa,
            link=link,
            notificacoes=notificacoes
        )

    db.session.commit()
