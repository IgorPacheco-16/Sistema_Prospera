from datetime import datetime, timedelta
from collections import defaultdict

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy.orm import selectinload

from database.models import db, HistoricoOP, Notificacao, OP, OPSetor, Setor, Tarefa, TarefaEsperaSolicitacao, TarefaObservacao, TarefaResponsavel, TarefaSolicitacao, User
from pacheco_security import exigir_op_mutavel, op_esta_encerrada
from tempo import agora_brasilia, hoje_brasilia


def create_ops_blueprint(
    login_required,
    tipos_permitidos,
    is_admin,
    is_atendente,
    usuario_pode_acionar_tarefa,
    usuario_pode_validar_tarefa,
    usuario_pode_observar_tarefa,
    criar_notificacao,
    mensagem_op,
    link_op,
    enviar_email_operacional,
    registrar_historico
):
    ops_bp = Blueprint("ops_bp", __name__)

    def sincronizar_setores_op(op):
        setores_selecionados = {
            int(setor_id)
            for setor_id in request.form.getlist("setores")
            if setor_id
        }
        setores_atuais = {op_setor.setor_id for op_setor in op.op_setores}
        setores_bloqueados = []

        for setor_id in setores_selecionados - setores_atuais:
            setor = db.session.get(Setor, setor_id)
            if not setor:
                continue

            db.session.add(OPSetor(
                op_id=op.id,
                setor_id=setor_id
            ))
            registrar_historico(
                op.id,
                "Setor adicionado",
                f"Setor {setor.nome} adicionado a OP."
            )

        for op_setor in list(op.op_setores):
            if op_setor.setor_id in setores_selecionados:
                continue

            tem_tarefas = Tarefa.query.filter_by(
                op_id=op.id,
                setor_id=op_setor.setor_id
            ).first()

            if tem_tarefas:
                nome_setor = op_setor.setor.nome if op_setor.setor else op_setor.setor_id
                setores_bloqueados.append(nome_setor)
                continue

            nome_setor = op_setor.setor.nome if op_setor.setor else op_setor.setor_id
            db.session.delete(op_setor)
            registrar_historico(
                op.id,
                "Setor removido",
                f"Setor {nome_setor} removido da OP."
            )

        if setores_bloqueados:
            flash(
                "Nao foi possivel remover setor(es) com tarefas vinculadas: "
                + ", ".join(str(setor) for setor in setores_bloqueados)
                + ".",
                "warning"
            )

    @ops_bp.route("/arquivadas")
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def arquivadas():
        ops = OP.query.filter_by(status="ARQUIVADA").all()
        return render_template("arquivadas/index.html", ops=ops)

    @ops_bp.route("/criar_op", methods=["GET", "POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def criar_op():
        if request.method == "POST":
            nome = request.form.get("nome")
            cliente = request.form.get("cliente", "").strip() or None
            prazo = request.form.get("prazo")
            alta_prioridade = request.form.get("alta_prioridade") == "on"
            caminho_pasta = request.form.get("caminho_pasta", "").strip() or None
            setores = request.form.getlist("setores")

            prazo_convertido = None
            if prazo:
                prazo_convertido = datetime.strptime(prazo, "%Y-%m-%d").date()

            limite_duplicidade = agora_brasilia() - timedelta(seconds=5)
            op_duplicada = (
                OP.query
                .filter(
                    OP.nome == nome,
                    OP.cliente == cliente,
                    OP.prazo_final == prazo_convertido,
                    OP.atendente == session.get("usuario"),
                    OP.criada_em >= limite_duplicidade,
                )
                .order_by(OP.criada_em.desc())
                .first()
            )
            if op_duplicada:
                flash("Esta ação já foi processada.", "info")
                return redirect(url_for("ver_op", id=op_duplicada.id))

            nova_op = OP(
                nome=nome,
                cliente=cliente,
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

        return render_template("op/criar.html", setores=Setor.query.order_by(Setor.nome).all())

    @ops_bp.route("/op/<int:id>")
    @login_required
    def ver_op(id):
        op = (
            OP.query
            .options(
                selectinload(OP.op_setores).selectinload(OPSetor.setor),
                selectinload(OP.tarefas).selectinload(Tarefa.responsaveis),
                selectinload(OP.tarefas).selectinload(Tarefa.criado_por),
                selectinload(OP.tarefas)
                .selectinload(Tarefa.responsavel_vinculos)
                .selectinload(TarefaResponsavel.usuario),
                selectinload(OP.tarefas)
                .selectinload(Tarefa.espera_solicitacoes)
                .selectinload(TarefaEsperaSolicitacao.solicitado_por),
                selectinload(OP.tarefas)
                .selectinload(Tarefa.espera_solicitacoes)
                .selectinload(TarefaEsperaSolicitacao.respondido_por),
                selectinload(OP.tarefas).selectinload(Tarefa.espera_solicitacao_atual),
                selectinload(OP.tarefas)
                .selectinload(Tarefa.observacoes)
                .selectinload(TarefaObservacao.autor),
                selectinload(OP.solicitacoes_tarefa).selectinload(TarefaSolicitacao.setor_solicitante),
                selectinload(OP.solicitacoes_tarefa).selectinload(TarefaSolicitacao.setor_destino),
                selectinload(OP.solicitacoes_tarefa).selectinload(TarefaSolicitacao.solicitado_por),
                selectinload(OP.solicitacoes_tarefa).selectinload(TarefaSolicitacao.respondido_por),
            )
            .filter(OP.id == id)
            .first()
        )
        if not op:
            abort(404)

        tipo_usuario = session.get("tipo")
        setor_usuario_id = session.get("setor_id")
        try:
            setor_usuario_id_int = int(setor_usuario_id)
        except (TypeError, ValueError):
            setor_usuario_id_int = None
        usuario_logado = User.query.filter_by(
            email=session.get("usuario"),
            ativo=True
        ).first()
        op_mutavel = not op_esta_encerrada(op)
        if tipo_usuario == "SETOR":
            if not op_mutavel:
                abort(403)

        estrutura = []
        op_setor_ids = {op_setor.setor_id for op_setor in op.op_setores}
        setores = Setor.query.order_by(Setor.nome).all()
        setores_por_id = {setor.id: setor for setor in setores}

        def tarefa_tem_setor_padrao(tarefa, tipo):
            setores_padrao = {
                "PCP": "pcp",
                "ATENDENTE": "atendimento",
            }
            setor_padrao = setores_padrao.get(tipo)
            if not setor_padrao:
                return False
            setor = setores_por_id.get(tarefa.setor_id)
            nome_setor = (getattr(setor, "nome", "") or "").strip().lower()
            return nome_setor == setor_padrao

        def usuario_setor_pode_atuar_tarefa(tarefa):
            return (
                setor_usuario_id_int is not None
                and setor_usuario_id_int == tarefa.setor_id
                and setor_usuario_id_int in op_setor_ids
            )

        def usuario_pode_acionar_tarefa_cache(tarefa):
            if tipo_usuario == "ADMIN":
                return True
            if tipo_usuario == "ESPECTADOR":
                return False
            if tipo_usuario == "SETOR":
                return usuario_setor_pode_atuar_tarefa(tarefa)

            responsaveis = list(getattr(tarefa, "responsaveis", []) or [])
            if responsaveis:
                if usuario_logado and any(
                    responsavel.id == usuario_logado.id
                    for responsavel in responsaveis
                ):
                    return True
                if tipo_usuario in {"PCP", "ATENDENTE"}:
                    return tarefa_tem_setor_padrao(tarefa, tipo_usuario)
                return False

            return tarefa_tem_setor_padrao(tarefa, tipo_usuario)

        def usuario_pode_observar_tarefa_cache(tarefa):
            if tipo_usuario in {"ADMIN", "PCP", "ATENDENTE"}:
                return True
            if tipo_usuario != "SETOR":
                return False
            return usuario_setor_pode_atuar_tarefa(tarefa)

        usuarios_por_setor = {
            setor_id: usuarios
            for setor_id, usuarios in agrupar_usuarios_ativos_por_setor().items()
        }
        op_ativa_para_solicitacao = op_mutavel
        pode_solicitar_tarefa_op = (
            tipo_usuario == "SETOR"
            and usuario_logado is not None
            and usuario_logado.setor_id == setor_usuario_id
            and op_ativa_para_solicitacao
            and setor_usuario_id_int in op_setor_ids
        )
        setores_para_solicitar_tarefa = []
        if pode_solicitar_tarefa_op:
            setores_para_solicitar_tarefa = sorted(
                [
                    op_setor.setor
                    for op_setor in op.op_setores
                    if op_setor.setor and op_setor.setor_id != setor_usuario_id
                ],
                key=lambda setor: setor.nome.casefold(),
            )

        solicitacoes_visiveis = []
        for solicitacao in op.solicitacoes_tarefa:
            solicitacao.pode_responder = (
                tipo_usuario in {"ADMIN", "PCP"}
                and solicitacao.status == "PENDENTE"
            )
            solicitacoes_visiveis.append(solicitacao)

        solicitacoes_por_setor = defaultdict(list)
        for solicitacao in sorted(
            solicitacoes_visiveis,
            key=lambda item: (item.solicitado_em, item.id),
        ):
            solicitacoes_por_setor[solicitacao.setor_destino_id].append(solicitacao)

        op_setores = sorted(
            op.op_setores,
            key=lambda op_setor: (op_setor.setor.nome if op_setor.setor else "").casefold()
        )

        tarefas_por_setor = defaultdict(list)
        for tarefa in op.tarefas:
            tarefas_por_setor[tarefa.setor_id].append(tarefa)

        for op_setor in op_setores:
            setor = op_setor.setor

            tarefas = sorted(
                tarefas_por_setor.get(setor.id, []),
                key=lambda tarefa: tarefa.id
            )
            for tarefa in tarefas:
                tarefa.pode_acionar = (
                    op_mutavel and usuario_pode_acionar_tarefa_cache(tarefa)
                )
                tarefa.pode_validar = op_mutavel and usuario_pode_validar_tarefa(tarefa)
                tarefa.pode_repassar = (
                    op_mutavel and (
                        tipo_usuario in {"ADMIN", "PCP"}
                        or (
                            tipo_usuario == "SETOR"
                            and usuario_pode_acionar_tarefa_cache(tarefa)
                        )
                    )
                )
                tarefa.espera_pendente = next(
                    (
                        solicitacao
                        for solicitacao in getattr(tarefa, "espera_solicitacoes", []) or []
                        if solicitacao.ativo and solicitacao.status == "PENDENTE"
                    ),
                    None,
                )
                tarefa.espera_ativa = (
                    tarefa.espera_solicitacao_atual
                    if tarefa.espera_solicitacao_atual
                    and tarefa.espera_solicitacao_atual.ativo
                    and tarefa.espera_solicitacao_atual.status == "APROVADA"
                    else None
                )
                tarefa.pode_solicitar_espera = (
                    op_mutavel
                    and (
                        tipo_usuario in {"ADMIN", "PCP", "ATENDENTE"}
                        or (
                            tipo_usuario == "SETOR"
                            and usuario_pode_acionar_tarefa_cache(tarefa)
                        )
                    )
                )
                tarefa.pode_responder_espera = op_mutavel and tipo_usuario in {"ADMIN", "PCP", "ATENDENTE"}
                tarefa.pode_adicionar_observacao = (
                    usuario_pode_observar_tarefa_cache(tarefa)
                    and op_ativa_para_solicitacao
                )
                tarefa.observacoes_ativas = [
                    observacao
                    for observacao in getattr(tarefa, "observacoes", []) or []
                    if observacao.deletada_em is None
                ]
                tarefa.responsaveis_ordenados = sorted(
                    list(getattr(tarefa, "responsaveis", []) or []),
                    key=lambda usuario: ((usuario.nome or usuario.email or "").casefold(), usuario.id),
                )
                tarefa.vinculos_responsaveis_ordenados = sorted(
                    [
                        vinculo
                        for vinculo in getattr(tarefa, "responsavel_vinculos", []) or []
                        if vinculo.status != "REMOVIDO"
                    ],
                    key=lambda vinculo: (
                        0 if vinculo.status == "ACEITO" else 1 if vinculo.status in {"PENDENTE", "APROVADO"} else 2,
                        (vinculo.usuario.nome or vinculo.usuario.email or "").casefold()
                        if vinculo.usuario else "",
                        vinculo.id,
                    ),
                )
                tarefa.vinculos_responsaveis_contabilizados = [
                    vinculo
                    for vinculo in tarefa.vinculos_responsaveis_ordenados
                    if (
                        vinculo.ativo
                        and (
                            vinculo.status == "ACEITO"
                            or (vinculo.status == "PENDENTE" and vinculo.tipo != "REPASSE")
                        )
                    )
                ]
                tarefa.responsaveis_contabilizados_total = len(
                    tarefa.vinculos_responsaveis_contabilizados
                )
                tarefa.responsaveis_contabilizados_ids = {
                    vinculo.usuario_id
                    for vinculo in tarefa.vinculos_responsaveis_contabilizados
                }
                tarefa.responsaveis_atuais_ids = {
                    responsavel.id
                    for responsavel in tarefa.responsaveis_ordenados
                }
                tarefa.usuario_logado_id = usuario_logado.id if usuario_logado else None
                tarefa.repasse_pendente_usuario = next(
                    (
                        vinculo
                        for vinculo in tarefa.vinculos_responsaveis_ordenados
                        if usuario_logado
                        and vinculo.usuario_id == usuario_logado.id
                        and vinculo.status == "PENDENTE"
                        and vinculo.ativo
                    ),
                    None,
                )

            estrutura.append({
                "setor": setor,
                "tarefas": tarefas,
                "solicitacoes_tarefa": solicitacoes_por_setor.get(setor.id, []),
                "usuarios": usuarios_por_setor.get(setor.id, []),
                "total": len(tarefas),
                "validadas": sum(1 for t in tarefas if t.validado),
                "pode_acionar": all(
                    usuario_pode_acionar_tarefa_cache(tarefa)
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
            setores=setores,
            op_mutavel=op_mutavel,
            pode_finalizar_op=(
                op_mutavel
                and tipo_usuario in {"ATENDENTE", "ADMIN"}
                and all(tarefa.validado for tarefa in op.tarefas)
            ),
            pode_solicitar_tarefa_op=pode_solicitar_tarefa_op,
            setores_para_solicitar_tarefa=setores_para_solicitar_tarefa,
            tipo=tipo_usuario,
            today=hoje_brasilia(),
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

        setores = Setor.query.order_by(Setor.nome).all()

        if request.method == "POST":
            op_bloqueada = exigir_op_mutavel(op, "OP finalizada ou arquivada nao permite edicao")
            if op_bloqueada:
                return op_bloqueada

            nome_anterior = op.nome
            cliente_anterior = op.cliente
            prazo_anterior = op.prazo_final
            prioridade_anterior = op.alta_prioridade
            caminho_pasta_anterior = op.caminho_pasta

            op.nome = request.form.get("nome")
            op.cliente = request.form.get("cliente", "").strip() or None
            op.alta_prioridade = request.form.get("alta_prioridade") == "on"
            op.caminho_pasta = request.form.get("caminho_pasta", "").strip() or None

            prazo = request.form.get("prazo")
            if prazo:
                op.prazo_final = datetime.strptime(prazo, "%Y-%m-%d").date()
            else:
                op.prazo_final = None

            sincronizar_setores_op(op)

            mudancas = []
            if nome_anterior != op.nome:
                mudancas.append("nome")
            if cliente_anterior != op.cliente:
                mudancas.append("cliente")
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

    @ops_bp.route("/op/<int:id>/setores", methods=["GET", "POST"])
    @tipos_permitidos("ATENDENTE", "PCP", "ADMIN")
    def configurar_setores_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)

        setores = Setor.query.order_by(Setor.nome).all()

        if request.method == "POST":
            op_bloqueada = exigir_op_mutavel(op, "OP finalizada ou arquivada nao permite configurar setores")
            if op_bloqueada:
                return op_bloqueada

            sincronizar_setores_op(op)
            db.session.commit()
            flash("Setores da OP atualizados.", "success")
            return redirect(url_for("ver_op", id=op.id))

        return render_template(
            "op/setores.html",
            op=op,
            setores=setores,
            tipo=session.get("tipo"),
        )

    @ops_bp.route("/finalizar_op/<int:id>", methods=["POST"])
    @tipos_permitidos("ATENDENTE", "ADMIN")
    def finalizar_op(id):
        op = db.session.get(OP, id)
        if not op:
            abort(404)
        op_bloqueada = exigir_op_mutavel(op, "OP finalizada ou arquivada nao permite finalizar")
        if op_bloqueada:
            return op_bloqueada

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


def agrupar_usuarios_ativos_por_setor():
    usuarios_por_setor = defaultdict(list)
    usuarios = (
        User.query
        .filter(User.ativo.is_(True), User.setor_id.isnot(None))
        .order_by(User.nome, User.email)
        .all()
    )
    for usuario in usuarios:
        usuarios_por_setor[usuario.setor_id].append(usuario)
    return usuarios_por_setor
