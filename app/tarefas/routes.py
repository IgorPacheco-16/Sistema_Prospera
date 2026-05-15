from datetime import datetime

from flask import Blueprint, redirect, request, session, url_for

from database.models import db, OP, OPSetor, Tarefa


def create_tarefas_blueprint(
    tipos_permitidos,
    is_setor,
    criar_notificacao,
    link_tarefa,
    registrar_historico
):
    tarefas_bp = Blueprint("tarefas_bp", __name__)

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

        nova = Tarefa(
            op_id=op_id,
            setor_id=setor_id,
            nome=nome,
            prazo=datetime.strptime(prazo, "%Y-%m-%d").date() if prazo else None,
            liberada=True
        )

        db.session.add(nova)
        db.session.flush()

        op = db.session.get(OP, op_id)
        if op:
            criar_notificacao(
                "SETOR",
                f"Nova tarefa criada: {nova.nome} na OP #{op.id} - {op.nome}",
                link=link_tarefa(op.id, setor_id, nova.id),
                op_id=op.id,
                tarefa_id=nova.id,
                setor_id=setor_id,
                tipo_evento="tarefa_criada"
            )
            registrar_historico(
                op.id,
                "Tarefa criada",
                f"Tarefa '{nova.nome}' criada para o setor {setor_vinculado.setor.nome}."
            )

        db.session.commit()

        return redirect(request.referrer)

    @tarefas_bp.route("/entregar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("SETOR", "ADMIN")
    def entregar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)

        if is_setor() and session.get("setor_id") != tarefa.setor_id:
            return "Setor incorreto", 403

        tarefa.entregue = True
        tarefa.validado = False

        op = db.session.get(OP, tarefa.op_id)
        if op:
            mensagem = f"Tarefa entregue aguardando validação: {tarefa.setor.nome} na OP #{op.id} - {op.nome}"
            link = link_tarefa(op.id, tarefa.setor_id, tarefa.id)
            criar_notificacao(
                "ATENDENTE",
                mensagem,
                link=link,
                op_id=op.id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento="tarefa_aguardando_validacao"
            )
            criar_notificacao(
                "PCP",
                mensagem,
                link=link,
                op_id=op.id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento="tarefa_aguardando_validacao"
            )
            registrar_historico(
                op.id,
                "Tarefa aguardando validação",
                f"Tarefa '{tarefa.nome}' enviada para validação pelo setor {tarefa.setor.nome}."
            )

        db.session.commit()

        return redirect(request.referrer)

    @tarefas_bp.route("/validar_tarefa/<int:id>", methods=["POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def validar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)

        if not tarefa.entregue:
            return "Precisa entregar antes"

        tarefa.validado = True

        op = db.session.get(OP, tarefa.op_id)
        if op:
            criar_notificacao(
                "SETOR",
                f"Entrega validada: {tarefa.nome} na OP #{op.id} - {op.nome}",
                link=link_tarefa(op.id, tarefa.setor_id, tarefa.id),
                op_id=op.id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento="entrega_validada"
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

        tarefa.nome = request.form.get("nome")

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
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def recusar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)
        tarefa.entregue = False
        tarefa.validado = False

        op = db.session.get(OP, tarefa.op_id)
        if op:
            criar_notificacao(
                "SETOR",
                f"Entrega recusada: {tarefa.nome} na OP #{op.id} - {op.nome}",
                link=link_tarefa(op.id, tarefa.setor_id, tarefa.id),
                op_id=op.id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento="entrega_recusada"
            )
            registrar_historico(
                op.id,
                "Entrega recusada",
                f"Entrega da tarefa '{tarefa.nome}' recusada."
            )

        db.session.commit()

        return redirect(request.referrer)

    return tarefas_bp
