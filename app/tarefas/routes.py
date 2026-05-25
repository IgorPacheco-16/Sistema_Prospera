from datetime import datetime

from flask import Blueprint, current_app, jsonify, redirect, request, url_for

from database.models import db, OP, OPSetor, Tarefa, User
from tempo import agora_brasilia


STATUS_PENDENTE = "PENDENTE"
STATUS_EM_ANDAMENTO = "EM ANDAMENTO"
STATUS_EM_VALIDACAO = "EM VALIDAÇÃO"
STATUS_ENTREGUE = "ENTREGUE"
MAX_RESPONSAVEIS_TAREFA = 4


def status_atual_tarefa(tarefa):
    if tarefa.validado:
        return STATUS_ENTREGUE
    if tarefa.entregue:
        return STATUS_EM_VALIDACAO
    return tarefa.status or STATUS_PENDENTE


def aplicar_status_tarefa(tarefa, status):
    tarefa.status = status

    if status == STATUS_ENTREGUE:
        tarefa.entregue = True
        tarefa.validado = True
    elif status == STATUS_EM_VALIDACAO:
        tarefa.entregue = True
        tarefa.validado = False
    else:
        tarefa.entregue = False
        tarefa.validado = False


def preencher_data_se_vazia(objeto, atributo, valor):
    if getattr(objeto, atributo) is None:
        setattr(objeto, atributo, valor)


def usuarios_ativos_do_setor(setor_id):
    return (
        User.query
        .filter_by(setor_id=setor_id, ativo=True)
        .order_by(User.nome, User.email)
        .all()
    )


def ids_responsaveis_formulario():
    valores = request.form.getlist("responsaveis")
    valores.extend(request.form.getlist("responsaveis[]"))

    ids = []
    for valor in valores:
        valor = (valor or "").strip()
        if not valor:
            continue
        try:
            usuario_id = int(valor)
        except (TypeError, ValueError):
            return None, ("Responsavel invalido para este setor", 400)
        if usuario_id not in ids:
            ids.append(usuario_id)

    return ids, None


def validar_responsaveis_formulario(setor_id):
    usuario_ids, erro = ids_responsaveis_formulario()
    if erro:
        return [], erro

    if len(usuario_ids) > MAX_RESPONSAVEIS_TAREFA:
        return [], ("Selecione no maximo 4 responsaveis por tarefa", 400)

    if not usuario_ids:
        return [], None

    responsaveis = (
        User.query
        .filter(
            User.id.in_(usuario_ids),
            User.ativo.is_(True),
            User.setor_id == setor_id,
        )
        .order_by(User.nome, User.email)
        .all()
    )

    if {usuario.id for usuario in responsaveis} != set(usuario_ids):
        return [], ("Responsavel invalido para este setor", 400)

    return responsaveis, None


def responsaveis_ordenados(tarefa):
    return sorted(
        list(getattr(tarefa, "responsaveis", []) or []),
        key=lambda usuario: ((usuario.nome or usuario.email or "").casefold(), usuario.id),
    )


def usuarios_notificacao_tarefa(tarefa):
    responsaveis = [
        responsavel
        for responsavel in responsaveis_ordenados(tarefa)
        if responsavel.ativo
    ]
    if responsaveis:
        emails = []
        for responsavel in responsaveis:
            email = (responsavel.email or "").strip().lower()
            if not email or "@" not in email:
                current_app.logger.warning(
                    "notificacao_tarefa_responsavel_sem_email_valido tarefa_id=%s usuario_id=%s",
                    tarefa.id,
                    responsavel.id,
                )
                continue
            if email not in emails:
                emails.append(email)
        return emails
    return ["SETOR"]


def criar_notificacoes_tarefa(criar_notificacao, tarefa, mensagem, link, tipo_evento):
    notificacoes = []
    for usuario in usuarios_notificacao_tarefa(tarefa):
        notificacao = criar_notificacao(
            usuario,
            mensagem,
            link=link,
            op_id=tarefa.op_id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento=tipo_evento
        )
        notificacoes.append(notificacao)
    return notificacoes


def create_tarefas_blueprint(
    tipos_permitidos,
    is_setor,
    usuario_pode_acionar_tarefa,
    criar_notificacao,
    mensagem_tarefa,
    link_tarefa,
    enviar_email_operacional,
    registrar_historico
):
    tarefas_bp = Blueprint("tarefas_bp", __name__)

    def exigir_permissao_tarefa(tarefa):
        if not usuario_pode_acionar_tarefa(tarefa):
            if not is_setor():
                return "Acesso negado para esta tarefa", 403

            return "Setor incorreto", 403

        return None

    @tarefas_bp.route("/api/setores/<int:setor_id>/usuarios")
    @tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
    def usuarios_ativos_setor(setor_id):
        usuarios = usuarios_ativos_do_setor(setor_id)
        return jsonify({
            "usuarios": [
                {
                    "id": usuario.id,
                    "nome": usuario.nome or usuario.email,
                    "email": usuario.email,
                }
                for usuario in usuarios
            ]
        })

    @tarefas_bp.route("/criar_tarefa/<int:op_id>/<int:setor_id>", methods=["POST"])
    @tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
    def criar_tarefa(op_id, setor_id):
        setor_vinculado = OPSetor.query.filter_by(
            op_id=op_id,
            setor_id=setor_id
        ).first()

        if not setor_vinculado:
            return "Setor não vinculado a esta OP", 400

        nome = request.form.get("nome")
        prazo = request.form.get("prazo")
        responsaveis, erro_responsavel = validar_responsaveis_formulario(setor_id)
        if erro_responsavel:
            return erro_responsavel

        nova = Tarefa(
            op_id=op_id,
            setor_id=setor_id,
            nome=nome,
            prazo=datetime.strptime(prazo, "%Y-%m-%d").date() if prazo else None,
            status=STATUS_PENDENTE,
            liberada=True,
            criada_em=agora_brasilia()
        )

        db.session.add(nova)
        db.session.flush()
        nova.responsaveis = responsaveis

        op = db.session.get(OP, op_id)
        if op:
            criar_notificacoes_tarefa(
                criar_notificacao,
                nova,
                mensagem_tarefa("tarefa_criada", op, nova),
                link_tarefa(op.id, setor_id, nova.id),
                "tarefa_criada"
            )
            registrar_historico(
                op.id,
                "Tarefa criada",
                f"Tarefa '{nova.nome}' criada para o setor {setor_vinculado.setor.nome}."
            )

        db.session.commit()

        return redirect(request.referrer)

    @tarefas_bp.route("/iniciar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("SETOR", "PCP", "ATENDENTE", "ADMIN")
    def iniciar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)

        acesso_negado = exigir_permissao_tarefa(tarefa)
        if acesso_negado:
            return acesso_negado

        if status_atual_tarefa(tarefa) != STATUS_PENDENTE:
            return "A tarefa precisa estar pendente para iniciar", 400

        agora = agora_brasilia()
        aplicar_status_tarefa(tarefa, STATUS_EM_ANDAMENTO)
        preencher_data_se_vazia(tarefa, "iniciada_em", agora)

        op = db.session.get(OP, tarefa.op_id)
        if op:
            mensagem = mensagem_tarefa("tarefa_em_andamento", op, tarefa)
            link = link_tarefa(op.id, tarefa.setor_id, tarefa.id)
            usuarios_notificacao = usuarios_notificacao_tarefa(tarefa)
            if usuarios_notificacao == ["SETOR"]:
                usuarios_notificacao = ["ATENDENTE", "PCP"]
            for usuario in usuarios_notificacao:
                criar_notificacao(
                    usuario,
                    mensagem,
                    link=link,
                    op_id=op.id,
                    tarefa_id=tarefa.id,
                    setor_id=tarefa.setor_id,
                    tipo_evento="tarefa_em_andamento"
                )
            registrar_historico(
                op.id,
                "Tarefa em andamento",
                f"Tarefa '{tarefa.nome}' iniciada pelo setor {tarefa.setor.nome}."
            )

        db.session.commit()
        return redirect(request.referrer)

    @tarefas_bp.route("/entregar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("SETOR", "PCP", "ATENDENTE", "ADMIN")
    def entregar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)

        acesso_negado = exigir_permissao_tarefa(tarefa)
        if acesso_negado:
            return acesso_negado

        if status_atual_tarefa(tarefa) != STATUS_EM_ANDAMENTO:
            return "A tarefa precisa estar em andamento para enviar à validação", 400

        agora = agora_brasilia()
        aplicar_status_tarefa(tarefa, STATUS_EM_VALIDACAO)
        preencher_data_se_vazia(tarefa, "enviada_validacao_em", agora)
        preencher_data_se_vazia(tarefa, "entregue_em", agora)

        op = db.session.get(OP, tarefa.op_id)
        if op:
            mensagem = mensagem_tarefa("tarefa_aguardando_validacao", op, tarefa)
            link = link_tarefa(op.id, tarefa.setor_id, tarefa.id)
            if responsaveis_ordenados(tarefa):
                notificacoes = criar_notificacoes_tarefa(
                    criar_notificacao,
                    tarefa,
                    mensagem,
                    link,
                    "tarefa_aguardando_validacao"
                )
            else:
                notificacoes = [
                    criar_notificacao(
                        "ATENDENTE",
                        mensagem,
                        link=link,
                        op_id=op.id,
                        tarefa_id=tarefa.id,
                        setor_id=tarefa.setor_id,
                        tipo_evento="tarefa_aguardando_validacao"
                    ),
                    criar_notificacao(
                        "PCP",
                        mensagem,
                        link=link,
                        op_id=op.id,
                        tarefa_id=tarefa.id,
                        setor_id=tarefa.setor_id,
                        tipo_evento="tarefa_aguardando_validacao"
                    ),
                ]
            enviar_email_operacional(
                "tarefa_aguardando_validacao",
                op=op,
                tarefa=tarefa,
                link=link,
                notificacoes=notificacoes
            )
            registrar_historico(
                op.id,
                "Tarefa aguardando validação",
                f"Tarefa '{tarefa.nome}' enviada para validação pelo setor {tarefa.setor.nome}."
            )

        db.session.commit()

        return redirect(request.referrer)

    @tarefas_bp.route("/validar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("SETOR", "PCP", "ATENDENTE", "ADMIN")
    def validar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)

        acesso_negado = exigir_permissao_tarefa(tarefa)
        if acesso_negado:
            return acesso_negado

        if status_atual_tarefa(tarefa) != STATUS_EM_VALIDACAO:
            return "A tarefa precisa estar em validação", 400

        agora = agora_brasilia()
        aplicar_status_tarefa(tarefa, STATUS_ENTREGUE)
        preencher_data_se_vazia(tarefa, "validada_em", agora)
        preencher_data_se_vazia(tarefa, "concluida_em", agora)

        op = db.session.get(OP, tarefa.op_id)
        if op:
            criar_notificacoes_tarefa(
                criar_notificacao,
                tarefa,
                mensagem_tarefa("entrega_validada", op, tarefa),
                link_tarefa(op.id, tarefa.setor_id, tarefa.id),
                "entrega_validada"
            )
            registrar_historico(
                op.id,
                "Entrega validada",
                f"Entrega da tarefa '{tarefa.nome}' validada."
            )

        db.session.commit()

        return redirect(request.referrer)

    @tarefas_bp.route("/editar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
    def editar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)
        nome_anterior = tarefa.nome
        prazo_anterior = tarefa.prazo
        responsaveis_anteriores_ids = {usuario.id for usuario in tarefa.responsaveis}
        responsaveis, erro_responsavel = validar_responsaveis_formulario(tarefa.setor_id)
        if erro_responsavel:
            return erro_responsavel

        tarefa.nome = request.form.get("nome")
        tarefa.responsaveis = responsaveis

        prazo = request.form.get("prazo")
        if prazo:
            tarefa.prazo = datetime.strptime(prazo, "%Y-%m-%d").date()
        else:
            tarefa.prazo = None

        mudancas = []
        if nome_anterior != tarefa.nome:
            mudancas.append("nome")
        if prazo_anterior != tarefa.prazo:
            mudancas.append("prazo")
        if responsaveis_anteriores_ids != {usuario.id for usuario in responsaveis}:
            mudancas.append("responsaveis")

        if mudancas:
            registrar_historico(
                tarefa.op_id,
                "Tarefa editada",
                f"Tarefa '{tarefa.nome}' editada: {', '.join(mudancas)}."
            )

        db.session.commit()
        return redirect(request.referrer)

    @tarefas_bp.route("/excluir_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
    def excluir_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)
        op_id = tarefa.op_id
        nome_tarefa = tarefa.nome
        nome_setor = tarefa.setor.nome if tarefa.setor else tarefa.setor_id

        db.session.delete(tarefa)
        registrar_historico(
            op_id,
            "Tarefa excluída",
            f"Tarefa '{nome_tarefa}' do setor {nome_setor} excluída."
        )
        db.session.commit()

        return redirect(url_for("ver_op", id=op_id))

    @tarefas_bp.route("/recusar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
    def recusar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)
        motivo_recusa = request.form.get("motivo_recusa", "").strip()

        acesso_negado = exigir_permissao_tarefa(tarefa)
        if acesso_negado:
            return acesso_negado

        if not motivo_recusa:
            return "Motivo da recusa obrigatório", 400

        if status_atual_tarefa(tarefa) != STATUS_EM_VALIDACAO:
            return "A tarefa precisa estar em validação para recusar", 400

        agora = agora_brasilia()
        aplicar_status_tarefa(tarefa, STATUS_PENDENTE)
        preencher_data_se_vazia(tarefa, "recusada_em", agora)
        tarefa.motivo_recusa = motivo_recusa

        op = db.session.get(OP, tarefa.op_id)
        if op:
            mensagem = (
                mensagem_tarefa("entrega_recusada", op, tarefa)
                + f"\nMotivo: {motivo_recusa}"
            )
            criar_notificacoes_tarefa(
                criar_notificacao,
                tarefa,
                mensagem,
                link_tarefa(op.id, tarefa.setor_id, tarefa.id),
                "entrega_recusada"
            )
            registrar_historico(
                op.id,
                "Entrega recusada",
                f"Entrega da tarefa '{tarefa.nome}' recusada. Motivo: {motivo_recusa}"
            )

        db.session.commit()

        return redirect(request.referrer)

    return tarefas_bp
