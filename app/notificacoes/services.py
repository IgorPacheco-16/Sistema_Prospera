from datetime import date, timedelta

from flask import session

from database.models import db, Notificacao, OP, OPSetor, Tarefa


def link_op(op_id):
    return f"/op/{op_id}"


def link_tarefa(op_id, setor_id, tarefa_id):
    return f"/op/{op_id}?setor={setor_id}&tarefa={tarefa_id}"


def query_notificacoes_usuario():
    query = Notificacao.query.filter_by(usuario=session.get("tipo"))

    if session.get("tipo") == "SETOR":
        query = query.filter_by(setor_id=session.get("setor_id"))

    return query


def setores_da_op(op_id):
    return OPSetor.query.filter_by(op_id=op_id).all()


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
    return notificacao


def notificar_op_para_gestao(op, tipo_evento, mensagem):
    criar_notificacao(
        "ATENDENTE",
        mensagem,
        link=link_op(op.id),
        op_id=op.id,
        tipo_evento=tipo_evento
    )
    criar_notificacao(
        "PCP",
        mensagem,
        link=link_op(op.id),
        op_id=op.id,
        tipo_evento=tipo_evento
    )


def notificar_op_para_setores(op, tipo_evento, mensagem):
    for op_setor in setores_da_op(op.id):
        criar_notificacao(
            "SETOR",
            mensagem,
            link=f"/op/{op.id}?setor={op_setor.setor_id}",
            op_id=op.id,
            setor_id=op_setor.setor_id,
            tipo_evento=tipo_evento
        )


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

        mensagem = f"Tarefa atrasada: {t.setor.nome} na OP #{op.id} - {op.nome}"
        link = link_tarefa(op.id, t.setor_id, t.id)

        for usuario in ["ATENDENTE", "PCP"]:
            criar_notificacao(
                usuario,
                mensagem,
                link=link,
                op_id=op.id,
                tarefa_id=t.id,
                setor_id=t.setor_id,
                tipo_evento="tarefa_atrasada"
            )

        criar_notificacao(
            "SETOR",
            mensagem,
            link=link,
            op_id=op.id,
            tarefa_id=t.id,
            setor_id=t.setor_id,
            tipo_evento="tarefa_atrasada"
        )

    ops_atrasadas = OP.query.filter(
        OP.prazo_final < hoje,
        OP.status.notin_(["FINALIZADA", "ARQUIVADA"])
    ).all()

    for op in ops_atrasadas:
        mensagem = f"OP atrasada: OP #{op.id} - {op.nome}"
        notificar_op_para_gestao(op, "op_atrasada", mensagem)
        notificar_op_para_setores(op, "op_atrasada", mensagem)

    ops_urgentes = OP.query.filter(
        OP.prazo_final >= hoje,
        OP.prazo_final <= hoje + timedelta(days=2),
        OP.status.notin_(["FINALIZADA", "ARQUIVADA"])
    ).all()

    for op in ops_urgentes:
        mensagem = f"OP urgente: OP #{op.id} - {op.nome}"
        notificar_op_para_gestao(op, "op_urgente", mensagem)
        notificar_op_para_setores(op, "op_urgente", mensagem)


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

        mensagem = f"Tarefa aguardando validação: {tarefa.setor.nome} na OP #{op.id} - {op.nome}"
        link = link_tarefa(op.id, tarefa.setor_id, tarefa.id)

        for usuario in ["ATENDENTE", "PCP"]:
            criar_notificacao(
                usuario,
                mensagem,
                link=link,
                op_id=op.id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento="tarefa_aguardando_validacao"
            )

    db.session.commit()
