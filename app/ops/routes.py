from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from database.models import db, HistoricoOP, Notificacao, OP, OPSetor, Setor, Tarefa
from tempo import agora_brasilia


def create_ops_blueprint(
    login_required,
    tipos_permitidos,
    is_admin,
    is_atendente,
    usuario_pode_acionar_tarefa,
    criar_notificacao,
    mensagem_op,
    link_op,
    enviar_email_operacional,
    registrar_historico
):
    ops_bp = Blueprint("ops_bp", __name__)

    @ops_bp.route("/arquivadas")
    @login_required
    def arquivadas():
        if session.get("tipo") == "SETOR":
            abort(403)

        ops = OP.query.filter_by(status="ARQUIVADA").all()
        return render_template("arquivadas/index.html", ops=ops)

    @ops_bp.route("/criar_op", methods=["GET", "POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def criar_op():
        if request.method == "POST":
            nome = request.form.get("nome")
            prazo = request.form.get("prazo")
            alta_prioridade = request.form.get("alta_prioridade") == "on"
            caminho_pasta = request.form.get("caminho_pasta", "").strip() or None
            setores = request.form.getlist("setores")

            prazo_convertido = None
            if prazo:
                prazo_convertido = datetime.strptime(prazo, "%Y-%m-%d").date()

            nova_op = OP(
                nome=nome,
                prazo_final=prazo_convertido,
                status="EM ANDAMENTO",
                atendente=session.get("usuario"),
                alta_prioridade=alta_prioridade,
                caminho_pasta=caminho_pasta,
                criada_em=agora_brasilia()
            )

            db.session.add(nova_op)
            db.session.commit()

            for setor_id in setores:
                db.session.add(OPSetor(
                    op_id=nova_op.id,
                    setor_id=int(setor_id)
                ))

            notificacao_pcp = criar_notificacao(
                "PCP",
                mensagem_op("op_criada", nova_op),
                link=link_op(nova_op.id),
                op_id=nova_op.id,
                tipo_evento="op_criada"
            )
            enviar_email_operacional(
                "op_criada",
                op=nova_op,
                link=link_op(nova_op.id),
                notificacoes=[notificacao_pcp]
            )
            registrar_historico(
                nova_op.id,
                "OP criada",
                f"OP criada com {len(setores)} setor(es) participante(s)."
            )

            db.session.commit()

            return redirect(url_for("ver_op", id=nova_op.id))

        return render_template("op/criar.html", setores=Setor.query.all())

    @ops_bp.route("/op/<int:id>")
    @login_required
    def ver_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)

        tipo_usuario = session.get("tipo")
        setor_usuario_id = session.get("setor_id")
        if tipo_usuario == "SETOR":
            vinculo_setor = OPSetor.query.filter_by(
                op_id=op.id,
                setor_id=setor_usuario_id
            ).first()
            if not vinculo_setor:
                abort(403)

        estrutura = []

        op_setores = op.op_setores
        if tipo_usuario == "SETOR":
            op_setores = [
                op_setor
                for op_setor in op_setores
                if op_setor.setor_id == setor_usuario_id
            ]

        for op_setor in op_setores:
            setor = op_setor.setor

            tarefas = Tarefa.query.filter_by(
                op_id=op.id,
                setor_id=setor.id
            ).all()

            estrutura.append({
                "setor": setor,
                "tarefas": tarefas,
                "total": len(tarefas),
                "validadas": sum(1 for t in tarefas if t.validado),
                "pode_acionar": all(
                    usuario_pode_acionar_tarefa(tarefa)
                    for tarefa in tarefas
                ) if tarefas else (
                    session.get("tipo") != "SETOR"
                    or session.get("setor_id") == setor.id
                )
            })

        historico = HistoricoOP.query.filter_by(
            op_id=op.id
        ).order_by(HistoricoOP.data.desc()).limit(30).all()

        return render_template(
            "op/detalhe.html",
            op=op,
            estrutura=estrutura,
            historico=historico,
            setores=Setor.query.all(),
            tipo=tipo_usuario,
            today=date.today(),
            focus_setor_id=request.args.get("setor", type=int),
            focus_tarefa_id=request.args.get("tarefa", type=int)
        )

    @ops_bp.route("/arquivar_op/<int:id>", methods=["POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def arquivar_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)

        op.status = "ARQUIVADA"
        if op.arquivada_em is None:
            op.arquivada_em = agora_brasilia()
        registrar_historico(
            op.id,
            "OP arquivada",
            "OP arquivada."
        )
        db.session.commit()
        return redirect(url_for("dashboard"))

    @ops_bp.route("/excluir_op/<int:id>", methods=["POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def excluir_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)

        Tarefa.query.filter_by(op_id=id).delete()
        OPSetor.query.filter_by(op_id=id).delete()
        HistoricoOP.query.filter_by(op_id=id).delete()
        Notificacao.query.filter_by(op_id=id).delete()
        db.session.delete(op)
        db.session.commit()

        return redirect(url_for("arquivadas"))

    @ops_bp.route("/desarquivar_op/<int:id>", methods=["POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def desarquivar_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)

        op.status = "EM ANDAMENTO"
        registrar_historico(
            op.id,
            "OP desarquivada",
            "OP desarquivada e devolvida para em andamento."
        )
        db.session.commit()
        return redirect(url_for("arquivadas"))

    @ops_bp.route("/editar_op/<int:id>", methods=["GET", "POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def editar_op(id):
        pode_editar_op = is_atendente() or is_admin()

        op = db.session.get(OP, id)
        if not op:
            abort(404)

        setores = Setor.query.all()

        if request.method == "POST":
            nome_anterior = op.nome
            prazo_anterior = op.prazo_final
            prioridade_anterior = op.alta_prioridade
            caminho_pasta_anterior = op.caminho_pasta

            op.nome = request.form.get("nome")
            op.alta_prioridade = request.form.get("alta_prioridade") == "on"
            op.caminho_pasta = request.form.get("caminho_pasta", "").strip() or None

            prazo = request.form.get("prazo")
            if prazo:
                op.prazo_final = datetime.strptime(prazo, "%Y-%m-%d").date()
            else:
                op.prazo_final = None

            setores_selecionados = {int(setor_id) for setor_id in request.form.getlist("setores")}
            setores_atuais = {op_setor.setor_id for op_setor in op.op_setores}

            for setor_id in setores_selecionados - setores_atuais:
                setor = db.session.get(Setor, setor_id)
                db.session.add(OPSetor(
                    op_id=op.id,
                    setor_id=setor_id
                ))
                registrar_historico(
                    op.id,
                    "Setor adicionado",
                    f"Setor {setor.nome if setor else setor_id} adicionado à OP."
                )

            for op_setor in list(op.op_setores):
                if op_setor.setor_id in setores_selecionados:
                    continue

                tem_tarefas = Tarefa.query.filter_by(
                    op_id=op.id,
                    setor_id=op_setor.setor_id
                ).first()

                if tem_tarefas:
                    flash(
                        "Um ou mais setores com tarefas foram mantidos para proteger os dados da OP."
                    )
                else:
                    nome_setor = op_setor.setor.nome if op_setor.setor else op_setor.setor_id
                    db.session.delete(op_setor)
                    registrar_historico(
                        op.id,
                        "Setor removido",
                        f"Setor {nome_setor} removido da OP."
                    )

            mudancas = []
            if nome_anterior != op.nome:
                mudancas.append("nome")
            if prazo_anterior != op.prazo_final:
                mudancas.append("prazo final")
            if prioridade_anterior != op.alta_prioridade:
                mudancas.append("alta prioridade")
            if caminho_pasta_anterior != op.caminho_pasta:
                mudancas.append("caminho da pasta")

            if mudancas:
                registrar_historico(
                    op.id,
                    "OP editada",
                    "Dados da OP editados: " + ", ".join(mudancas) + "."
                )

            db.session.commit()
            return redirect(url_for("ver_op", id=op.id))

        return render_template(
            "op/editar.html",
            op=op,
            setores=setores,
            tipo=session.get("tipo"),
            pode_editar_op=pode_editar_op
        )

    @ops_bp.route("/finalizar_op/<int:id>", methods=["POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def finalizar_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)

        tarefas = Tarefa.query.filter_by(op_id=id).all()
        if tarefas and not all(t.validado for t in tarefas):
            return "Ainda existem tarefas pendentes de validação"

        op.status = "FINALIZADA"
        if op.finalizada_em is None:
            op.finalizada_em = agora_brasilia()
        registrar_historico(
            op.id,
            "OP finalizada",
            "OP finalizada."
        )
        db.session.commit()
        flash("OP Finalizada", "op_finalizada")
        return redirect(url_for("ver_op", id=op.id))

    return ops_bp
