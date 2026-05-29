from datetime import datetime, timedelta
from uuid import uuid4

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for

from database.models import db, OP, OPSetor, Tarefa, TarefaResponsavel, User
from tempo import agora_brasilia


STATUS_PENDENTE = "PENDENTE"
STATUS_EM_ANDAMENTO = "EM ANDAMENTO"
STATUS_EM_VALIDACAO = "EM VALIDAÇÃO"
STATUS_ENTREGUE = "ENTREGUE"
MAX_RESPONSAVEIS_TAREFA = 4
STATUS_RESPONSAVEL_PENDENTE = "PENDENTE"
STATUS_RESPONSAVEL_ACEITO = "ACEITO"
STATUS_RESPONSAVEL_APROVADO = "APROVADO"
STATUS_RESPONSAVEL_RECUSADO = "RECUSADO"
STATUS_RESPONSAVEL_CANCELADO = "CANCELADO"
STATUS_RESPONSAVEL_REMOVIDO = "REMOVIDO"
STATUS_RESPONSAVEL_CONTABILIZADO = {
    STATUS_RESPONSAVEL_ACEITO,
}
TIPO_ATRIBUICAO = "ATRIBUICAO"
TIPO_REPASSE = "REPASSE"
TIPO_INCLUSAO = "INCLUSAO"
TIPO_REMOCAO = "REMOCAO"
TIPOS_RESPONSAVEL = {TIPO_ATRIBUICAO, TIPO_REPASSE, TIPO_INCLUSAO, TIPO_REMOCAO}
PAPEL_REPASSE_ENTRADA = "ENTRADA"
PAPEL_REPASSE_SAIDA = "SAIDA"
STATUS_LOTE_REPASSE_PENDENTE = "PENDENTE"
STATUS_LOTE_REPASSE_CONCLUIDO = "CONCLUIDO"
STATUS_LOTE_REPASSE_RECUSADO = "RECUSADO"


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


def ids_responsaveis_tarefa(tarefa):
    return sorted(usuario.id for usuario in getattr(tarefa, "responsaveis", []) or [])


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


def usuario_logado_ativo():
    email = session.get("usuario")
    if not email:
        return None
    return User.query.filter_by(email=email, ativo=True).first()


def nome_usuario(usuario):
    return (getattr(usuario, "nome", None) or getattr(usuario, "email", None) or "").strip()


def vinculos_responsaveis_aceitos(tarefa):
    return [
        vinculo
        for vinculo in getattr(tarefa, "responsavel_vinculos", []) or []
        if vinculo.ativo and vinculo.status == STATUS_RESPONSAVEL_ACEITO
    ]


def vinculos_responsaveis_contabilizados(tarefa):
    return [
        vinculo
        for vinculo in getattr(tarefa, "responsavel_vinculos", []) or []
        if (
            vinculo.ativo
            and (
                vinculo.status == STATUS_RESPONSAVEL_ACEITO
                or (
                    vinculo.status == STATUS_RESPONSAVEL_PENDENTE
                    and vinculo.tipo != TIPO_REPASSE
                )
            )
        )
    ]


def vinculo_responsavel_existente(tarefa, usuario_id):
    for vinculo in vinculos_responsaveis_contabilizados(tarefa):
        if vinculo.usuario_id == usuario_id:
            return vinculo
    return None


def ids_usuarios_formulario_campos(campos, mensagem_vazio):
    valores = []
    for nome in campos:
        valores.extend(request.form.getlist(nome))

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

    if not ids:
        return None, (mensagem_vazio, 400)

    return ids, None


def ids_usuarios_repasse_formulario():
    valores_unicos = []
    usuario_id_unico = request.form.get("usuario_id") or request.form.get("responsavel_id")
    if usuario_id_unico:
        valores_unicos.append(usuario_id_unico)
    ids, erro = ids_usuarios_formulario_campos(
        ("usuario_ids", "usuario_ids[]", "responsaveis", "responsaveis[]"),
        "Selecione ao menos um responsavel"
    )
    if erro and valores_unicos:
        ids = []
    elif erro:
        return ids, erro

    for valor in valores_unicos:
        try:
            usuario_id = int((valor or "").strip())
        except (TypeError, ValueError):
            return None, ("Responsavel invalido para este setor", 400)
        if usuario_id not in ids:
            ids.append(usuario_id)

    if not ids:
        return None, ("Selecione ao menos um responsavel", 400)

    return ids, None


def ids_usuarios_saida_repasse_formulario(obrigatorio=True):
    mensagem = "Selecione ao menos um responsavel para sair"
    ids, erro = ids_usuarios_formulario_campos(
        ("sair_ids", "sair_ids[]", "saida_ids", "saida_ids[]"),
        mensagem
    )
    if erro and not obrigatorio and erro[0] == mensagem:
        return [], None
    return ids, erro


def usuario_pode_repassar_tarefa(tarefa):
    tipo = session.get("tipo")
    if tipo in {"ADMIN", "PCP"}:
        return True
    if tipo == "SETOR":
        try:
            return int(session.get("setor_id")) == tarefa.setor_id
        except (TypeError, ValueError):
            return False
    return False


def usuario_pode_responder_vinculo(vinculo):
    usuario = usuario_logado_ativo()
    return bool(usuario and usuario.id == vinculo.usuario_id)


def validar_usuarios_destino_repasse(tarefa, usuario_ids):
    vinculos_contabilizados = vinculos_responsaveis_contabilizados(tarefa)
    ids_vinculados = {vinculo.usuario_id for vinculo in vinculos_contabilizados}

    if len(vinculos_contabilizados) + len(usuario_ids) > MAX_RESPONSAVEIS_TAREFA:
        return [], ("A tarefa ja possui o maximo de 4 responsaveis", 400)

    if ids_vinculados.intersection(usuario_ids):
        return [], ("Este usuario ja esta vinculado a tarefa", 400)

    usuarios = (
        User.query
        .filter(User.id.in_(usuario_ids))
        .order_by(User.nome, User.email)
        .all()
    )

    if {usuario.id for usuario in usuarios} != set(usuario_ids):
        return None, ("Responsavel invalido para este setor", 400)

    for usuario in usuarios:
        if not usuario.ativo:
            return [], ("Responsavel invalido ou inativo", 400)
        if usuario.setor_id != tarefa.setor_id:
            return [], ("Responsavel invalido para este setor", 400)

    usuarios_por_id = {usuario.id: usuario for usuario in usuarios}
    return [usuarios_por_id[usuario_id] for usuario_id in usuario_ids], None


def validar_usuarios_entrada_repasse(tarefa, usuario_ids):
    ids_atuais = {vinculo.usuario_id for vinculo in vinculos_responsaveis_aceitos(tarefa)}
    if ids_atuais.intersection(usuario_ids):
        return [], ("Este usuario ja esta vinculado a tarefa", 400)

    usuarios, erro = validar_usuarios_setor_ativos(tarefa, usuario_ids)
    if erro:
        return usuarios, erro
    return usuarios, None


def validar_usuarios_saida_repasse(tarefa, usuario_ids):
    ids_atuais = {vinculo.usuario_id for vinculo in vinculos_responsaveis_aceitos(tarefa)}
    if not set(usuario_ids).issubset(ids_atuais):
        return [], ("Responsavel de saida invalido para esta tarefa", 400)

    usuarios, erro = validar_usuarios_setor_ativos(tarefa, usuario_ids)
    if erro:
        return usuarios, erro
    return usuarios, None


def validar_usuarios_setor_ativos(tarefa, usuario_ids):
    usuarios = (
        User.query
        .filter(User.id.in_(usuario_ids))
        .order_by(User.nome, User.email)
        .all()
    )

    if {usuario.id for usuario in usuarios} != set(usuario_ids):
        return None, ("Responsavel invalido para este setor", 400)

    for usuario in usuarios:
        if not usuario.ativo:
            return [], ("Responsavel invalido ou inativo", 400)
        if usuario.setor_id != tarefa.setor_id:
            return [], ("Responsavel invalido para este setor", 400)

    usuarios_por_id = {usuario.id: usuario for usuario in usuarios}
    return [usuarios_por_id[usuario_id] for usuario_id in usuario_ids], None


def validar_usuario_destino_repasse(tarefa, usuario_id):
    usuarios, erro = validar_usuarios_destino_repasse(tarefa, [usuario_id])
    if erro:
        return None, erro
    return usuarios[0], None


def mensagem_responsavel_pendente(op, tarefa, solicitante, observacao):
    mensagem = (
        "TAREFA PENDENTE DE ACEITE\n"
        f"OP: {op.nome if op else tarefa.op_id}\n"
        f"Tarefa: {tarefa.nome}\n"
        f"Solicitado por: {nome_usuario(solicitante) or 'Sistema'}"
    )
    if observacao:
        mensagem += f"\nObservacao: {observacao}"
    return mensagem


def notificar_solicitante(criar_notificacao, vinculo, mensagem, link, tipo_evento):
    solicitante = vinculo.solicitado_por
    email = (getattr(solicitante, "email", "") or "").strip().lower()
    if not email:
        return None
    return criar_notificacao(
        email,
        mensagem,
        link=link,
        op_id=vinculo.tarefa.op_id,
        tarefa_id=vinculo.tarefa_id,
        setor_id=vinculo.tarefa.setor_id,
        tipo_evento=tipo_evento,
    )


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


def repasse_pendente_tarefa(tarefa):
    return next(
        (
            vinculo
            for vinculo in getattr(tarefa, "responsavel_vinculos", []) or []
            if (
                vinculo.ativo
                and vinculo.tipo == TIPO_REPASSE
                and vinculo.repasse_lote_id
                and vinculo.repasse_status == STATUS_LOTE_REPASSE_PENDENTE
                and vinculo.status in {STATUS_RESPONSAVEL_PENDENTE, STATUS_RESPONSAVEL_APROVADO}
            )
        ),
        None,
    )


def mensagem_solicitacao_repasse(op, tarefa, solicitante, papel, observacao):
    acao = "entrada" if papel == PAPEL_REPASSE_ENTRADA else "saida"
    mensagem = (
        "REPASSE PENDENTE DE ACEITE\n"
        f"OP: {op.nome if op else tarefa.op_id}\n"
        f"Tarefa: {tarefa.nome}\n"
        f"Solicitacao de {acao}\n"
        f"Solicitado por: {nome_usuario(solicitante) or 'Sistema'}"
    )
    if observacao:
        mensagem += f"\nObservacao: {observacao}"
    return mensagem


def criar_vinculo_responsavel(
    tarefa,
    usuario,
    tipo,
    solicitante,
    observacao=None,
    repasse_lote_id=None,
    repasse_papel=None,
    repasse_status=None,
):
    vinculo = TarefaResponsavel(
        tarefa_id=tarefa.id,
        usuario_id=usuario.id,
        status=STATUS_RESPONSAVEL_PENDENTE,
        tipo=tipo,
        solicitado_por_id=solicitante.id if solicitante else None,
        solicitado_em=agora_brasilia(),
        observacao=observacao,
        ativo=True,
        repasse_lote_id=repasse_lote_id,
        repasse_papel=repasse_papel,
        repasse_status=repasse_status,
    )
    db.session.add(vinculo)
    db.session.flush()
    return vinculo


def vinculos_lote_repasse(lote_id):
    return (
        TarefaResponsavel.query
        .filter(TarefaResponsavel.repasse_lote_id == lote_id)
        .order_by(TarefaResponsavel.id)
        .all()
    )


def aplicar_lote_repasse(vinculo, criar_notificacao, link_tarefa, registrar_historico):
    tarefa = vinculo.tarefa
    lote = vinculos_lote_repasse(vinculo.repasse_lote_id)
    agora = agora_brasilia()
    entrada_ids = {
        item.usuario_id
        for item in lote
        if item.repasse_papel == PAPEL_REPASSE_ENTRADA
    }
    saida_ids = {
        item.usuario_id
        for item in lote
        if item.repasse_papel == PAPEL_REPASSE_SAIDA
    }

    for item in lote:
        item.respondido_em = item.respondido_em or agora
        item.repasse_status = STATUS_LOTE_REPASSE_CONCLUIDO
        if item.usuario_id in entrada_ids:
            item.status = STATUS_RESPONSAVEL_ACEITO
            item.ativo = True
        else:
            item.status = STATUS_RESPONSAVEL_ACEITO
            item.ativo = False

    for vinculo_atual in list(getattr(tarefa, "responsavel_vinculos", []) or []):
        if (
            vinculo_atual.usuario_id in saida_ids
            and vinculo_atual.status == STATUS_RESPONSAVEL_ACEITO
            and vinculo_atual.ativo
            and vinculo_atual.repasse_lote_id != vinculo.repasse_lote_id
        ):
            vinculo_atual.status = STATUS_RESPONSAVEL_REMOVIDO
            vinculo_atual.ativo = False
            vinculo_atual.respondido_em = agora

    op = db.session.get(OP, tarefa.op_id)
    link = link_tarefa(tarefa.op_id, tarefa.setor_id, tarefa.id)
    nomes_entrada = ", ".join(nome_usuario(item.usuario) for item in lote if item.usuario_id in entrada_ids)
    nomes_saida = ", ".join(nome_usuario(item.usuario) for item in lote if item.usuario_id in saida_ids)
    registrar_historico(
        tarefa.op_id,
        "Repasse concluido",
        f"Repasse da tarefa '{tarefa.nome}' concluido. Entraram: {nomes_entrada}. Sairam: {nomes_saida}."
    )
    notificar_solicitante(
        criar_notificacao,
        vinculo,
        (
            "REPASSE CONCLUIDO\n"
            f"OP: {op.nome if op else tarefa.op_id}\n"
            f"Tarefa: {tarefa.nome}\n"
            f"Entraram: {nomes_entrada}\n"
            f"Sairam: {nomes_saida}"
        ),
        link,
        f"tarefa_repasse_concluido_{vinculo.repasse_lote_id}",
    )


def cancelar_lote_repasse(vinculo, recusante, criar_notificacao, link_tarefa, registrar_historico):
    tarefa = vinculo.tarefa
    lote = vinculos_lote_repasse(vinculo.repasse_lote_id)
    agora = agora_brasilia()
    for item in lote:
        item.repasse_status = STATUS_LOTE_REPASSE_RECUSADO
        item.ativo = False
        if item.id != vinculo.id and item.status == STATUS_RESPONSAVEL_PENDENTE:
            item.status = STATUS_RESPONSAVEL_CANCELADO
        elif item.id != vinculo.id and item.status == STATUS_RESPONSAVEL_APROVADO:
            item.status = STATUS_RESPONSAVEL_CANCELADO
        item.respondido_em = item.respondido_em or agora

    op = db.session.get(OP, tarefa.op_id)
    link = link_tarefa(tarefa.op_id, tarefa.setor_id, tarefa.id)
    notificar_solicitante(
        criar_notificacao,
        vinculo,
        (
            "REPASSE RECUSADO\n"
            f"OP: {op.nome if op else tarefa.op_id}\n"
            f"Tarefa: {tarefa.nome}\n"
            f"Recusado por: {nome_usuario(recusante)}"
        ),
        link,
        f"tarefa_repasse_recusado_{vinculo.repasse_lote_id}",
    )
    registrar_historico(
        tarefa.op_id,
        "Repasse recusado",
        f"{nome_usuario(recusante)} recusou o repasse da tarefa '{tarefa.nome}'."
    )


def lote_repasse_pronto(vinculo):
    lote = vinculos_lote_repasse(vinculo.repasse_lote_id)
    return bool(lote) and all(item.status == STATUS_RESPONSAVEL_APROVADO for item in lote)


def create_tarefas_blueprint(
    tipos_permitidos,
    is_setor,
    usuario_pode_acionar_tarefa,
    usuario_pode_validar_tarefa,
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

    def exigir_permissao_validacao(tarefa):
        if not usuario_pode_validar_tarefa(tarefa):
            if not is_setor():
                return "Acesso negado para esta tarefa", 403

            return "Setor incorreto", 403

        return None

    @tarefas_bp.route("/tarefas/<int:id>/responsaveis", methods=["POST"])
    @tipos_permitidos("SETOR", "PCP", "ADMIN")
    def repassar_tarefa(id):
        tarefa = Tarefa.query.get_or_404(id)

        if not usuario_pode_repassar_tarefa(tarefa):
            return "Acesso negado para repassar esta tarefa", 403

        tipo = (request.form.get("tipo") or "REPASSE").strip().upper()
        if tipo not in TIPOS_RESPONSAVEL:
            tipo = TIPO_REPASSE

        observacao = request.form.get("observacao", "").strip() or None
        solicitante = usuario_logado_ativo()
        op = db.session.get(OP, tarefa.op_id)
        link = link_tarefa(tarefa.op_id, tarefa.setor_id, tarefa.id)

        if tipo == TIPO_REPASSE:
            if repasse_pendente_tarefa(tarefa):
                return "Ja existe um repasse pendente para esta tarefa", 400

            entrada_ids, erro = ids_usuarios_repasse_formulario()
            if erro:
                return erro

            saida_ids, erro = ids_usuarios_saida_repasse_formulario()
            if erro:
                return erro

            if set(entrada_ids).intersection(saida_ids):
                return "O mesmo usuario nao pode entrar e sair no mesmo repasse", 400

            usuarios_entrada, erro = validar_usuarios_entrada_repasse(tarefa, entrada_ids)
            if erro:
                return erro

            usuarios_saida, erro = validar_usuarios_saida_repasse(tarefa, saida_ids)
            if erro:
                return erro

            ids_atuais = {vinculo.usuario_id for vinculo in vinculos_responsaveis_aceitos(tarefa)}
            total_final = len((ids_atuais - set(saida_ids)) | set(entrada_ids))
            if total_final > MAX_RESPONSAVEIS_TAREFA:
                return "O repasse ultrapassa o limite de 4 responsaveis", 400

            lote_id = str(uuid4())
            for usuario_destino in usuarios_entrada:
                vinculo = criar_vinculo_responsavel(
                    tarefa,
                    usuario_destino,
                    TIPO_REPASSE,
                    solicitante,
                    observacao=observacao,
                    repasse_lote_id=lote_id,
                    repasse_papel=PAPEL_REPASSE_ENTRADA,
                    repasse_status=STATUS_LOTE_REPASSE_PENDENTE,
                )
                criar_notificacao(
                    usuario_destino.email,
                    mensagem_solicitacao_repasse(
                        op, tarefa, solicitante, PAPEL_REPASSE_ENTRADA, observacao
                    ),
                    link=link,
                    op_id=tarefa.op_id,
                    tarefa_id=tarefa.id,
                    setor_id=tarefa.setor_id,
                    tipo_evento=f"tarefa_repasse_entrada_{vinculo.id}",
                )

            for usuario_saida in usuarios_saida:
                vinculo = criar_vinculo_responsavel(
                    tarefa,
                    usuario_saida,
                    TIPO_REPASSE,
                    solicitante,
                    observacao=observacao,
                    repasse_lote_id=lote_id,
                    repasse_papel=PAPEL_REPASSE_SAIDA,
                    repasse_status=STATUS_LOTE_REPASSE_PENDENTE,
                )
                criar_notificacao(
                    usuario_saida.email,
                    mensagem_solicitacao_repasse(
                        op, tarefa, solicitante, PAPEL_REPASSE_SAIDA, observacao
                    ),
                    link=link,
                    op_id=tarefa.op_id,
                    tarefa_id=tarefa.id,
                    setor_id=tarefa.setor_id,
                    tipo_evento=f"tarefa_repasse_saida_{vinculo.id}",
                )

            registrar_historico(
                tarefa.op_id,
                "Repasse proposto",
                (
                    f"Repasse da tarefa '{tarefa.nome}' proposto por "
                    f"{nome_usuario(solicitante) or 'Sistema'}."
                )
            )
            db.session.commit()
            flash("Repasse criado como proposta pendente de aceite.", "info")
            return redirect(request.referrer or url_for(
                "ver_op",
                id=tarefa.op_id,
                setor=tarefa.setor_id,
                tarefa=tarefa.id,
            ))

        if tipo == TIPO_REMOCAO:
            saida_ids, erro = ids_usuarios_saida_repasse_formulario(obrigatorio=False)
            if erro:
                return erro
            if not saida_ids:
                saida_ids, erro = ids_usuarios_repasse_formulario()
                if erro:
                    return erro

            usuarios_destino, erro = validar_usuarios_saida_repasse(tarefa, saida_ids)
            if erro:
                return erro
        else:
            usuario_ids, erro = ids_usuarios_repasse_formulario()
            if erro:
                return erro

            usuarios_destino, erro = validar_usuarios_destino_repasse(tarefa, usuario_ids)
            if erro:
                return erro

        for usuario_destino in usuarios_destino:
            vinculo = criar_vinculo_responsavel(
                tarefa,
                usuario_destino,
                tipo,
                solicitante,
                observacao=observacao,
            )
            criar_notificacao(
                usuario_destino.email,
                mensagem_responsavel_pendente(op, tarefa, solicitante, observacao),
                link=link,
                op_id=tarefa.op_id,
                tarefa_id=tarefa.id,
                setor_id=tarefa.setor_id,
                tipo_evento=f"tarefa_repassada_{vinculo.id}",
            )
            registrar_historico(
                tarefa.op_id,
                "Tarefa repassada",
                (
                    f"Tarefa '{tarefa.nome}' direcionada para "
                    f"{nome_usuario(usuario_destino)} por {nome_usuario(solicitante) or 'Sistema'}."
                )
            )
        db.session.commit()
        total_convites = len(usuarios_destino)
        flash(
            (
                "1 convite criado como pendente de aceite."
                if total_convites == 1
                else f"{total_convites} convites criados como pendentes de aceite."
            ),
            "info"
        )
        return redirect(request.referrer or url_for(
            "ver_op",
            id=tarefa.op_id,
            setor=tarefa.setor_id,
            tarefa=tarefa.id,
        ))

    @tarefas_bp.route("/tarefas/responsaveis/<int:vinculo_id>/aceitar", methods=["POST"])
    @tipos_permitidos("SETOR", "PCP", "ATENDENTE", "ADMIN")
    def aceitar_tarefa_responsavel(vinculo_id):
        vinculo = TarefaResponsavel.query.get_or_404(vinculo_id)

        if not usuario_pode_responder_vinculo(vinculo):
            return "Acesso negado para responder este repasse", 403
        if not vinculo.esta_pendente():
            return "Este repasse nao esta pendente", 400

        if vinculo.tipo == TIPO_REPASSE and vinculo.repasse_lote_id:
            vinculo.status = STATUS_RESPONSAVEL_APROVADO
            vinculo.respondido_em = agora_brasilia()

            if lote_repasse_pronto(vinculo):
                aplicar_lote_repasse(
                    vinculo,
                    criar_notificacao,
                    link_tarefa,
                    registrar_historico,
                )

            db.session.commit()
            flash("Resposta registrada para o repasse.", "success")
            return redirect(request.referrer or url_for(
                "ver_op",
                id=vinculo.tarefa.op_id,
                setor=vinculo.tarefa.setor_id,
                tarefa=vinculo.tarefa.id,
            ))

        vinculo.status = STATUS_RESPONSAVEL_ACEITO
        vinculo.respondido_em = agora_brasilia()

        tarefa = vinculo.tarefa
        usuario = vinculo.usuario
        if vinculo.tipo == TIPO_REMOCAO:
            for vinculo_atual in list(getattr(tarefa, "responsavel_vinculos", []) or []):
                if (
                    vinculo_atual.usuario_id == vinculo.usuario_id
                    and vinculo_atual.id != vinculo.id
                    and vinculo_atual.status == STATUS_RESPONSAVEL_ACEITO
                    and vinculo_atual.ativo
                ):
                    vinculo_atual.status = STATUS_RESPONSAVEL_REMOVIDO
                    vinculo_atual.ativo = False
                    vinculo_atual.respondido_em = vinculo.respondido_em
            vinculo.ativo = False

        op = db.session.get(OP, tarefa.op_id)
        link = link_tarefa(tarefa.op_id, tarefa.setor_id, tarefa.id)
        notificar_solicitante(
            criar_notificacao,
            vinculo,
            (
                "REPASSE ACEITO\n"
                f"OP: {op.nome if op else tarefa.op_id}\n"
                f"Tarefa: {tarefa.nome}\n"
                f"Responsavel: {nome_usuario(usuario)}"
            ),
            link,
            f"tarefa_repasse_aceito_{vinculo.id}",
        )
        registrar_historico(
            tarefa.op_id,
            "Repasse aceito",
            f"{nome_usuario(usuario)} aceitou a tarefa '{tarefa.nome}'."
        )
        db.session.commit()
        flash("Tarefa aceita.", "success")
        return redirect(request.referrer or url_for(
            "ver_op",
            id=tarefa.op_id,
            setor=tarefa.setor_id,
            tarefa=tarefa.id,
        ))

    @tarefas_bp.route("/tarefas/responsaveis/<int:vinculo_id>/recusar", methods=["POST"])
    @tipos_permitidos("SETOR", "PCP", "ATENDENTE", "ADMIN")
    def recusar_tarefa_responsavel(vinculo_id):
        vinculo = TarefaResponsavel.query.get_or_404(vinculo_id)

        if not usuario_pode_responder_vinculo(vinculo):
            return "Acesso negado para responder este repasse", 403
        if not vinculo.esta_pendente():
            return "Este repasse nao esta pendente", 400

        observacao = request.form.get("observacao", "").strip()
        if observacao:
            vinculo.observacao = (
                f"{vinculo.observacao}\nRecusa: {observacao}"
                if vinculo.observacao else f"Recusa: {observacao}"
            )
        vinculo.status = STATUS_RESPONSAVEL_RECUSADO
        vinculo.ativo = False
        vinculo.respondido_em = agora_brasilia()

        tarefa = vinculo.tarefa
        usuario = vinculo.usuario
        if vinculo.tipo == TIPO_REPASSE and vinculo.repasse_lote_id:
            cancelar_lote_repasse(
                vinculo,
                usuario,
                criar_notificacao,
                link_tarefa,
                registrar_historico,
            )
            db.session.commit()
            flash("Repasse recusado e proposta cancelada.", "info")
            return redirect(request.referrer or url_for(
                "ver_op",
                id=tarefa.op_id,
                setor=tarefa.setor_id,
                tarefa=tarefa.id,
            ))

        op = db.session.get(OP, tarefa.op_id)
        link = link_tarefa(tarefa.op_id, tarefa.setor_id, tarefa.id)
        notificar_solicitante(
            criar_notificacao,
            vinculo,
            (
                "REPASSE RECUSADO\n"
                f"OP: {op.nome if op else tarefa.op_id}\n"
                f"Tarefa: {tarefa.nome}\n"
                f"Responsavel: {nome_usuario(usuario)}"
            ),
            link,
            f"tarefa_repasse_recusado_{vinculo.id}",
        )
        registrar_historico(
            tarefa.op_id,
            "Repasse recusado",
            f"{nome_usuario(usuario)} recusou a tarefa '{tarefa.nome}'."
        )
        db.session.commit()
        flash("Repasse recusado.", "info")
        return redirect(request.referrer or url_for(
            "ver_op",
            id=tarefa.op_id,
            setor=tarefa.setor_id,
            tarefa=tarefa.id,
        ))

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

        prazo_convertido = datetime.strptime(prazo, "%Y-%m-%d").date() if prazo else None
        responsaveis_ids = sorted(usuario.id for usuario in responsaveis)
        limite_duplicidade = agora_brasilia() - timedelta(seconds=5)
        tarefa_duplicada = None
        tarefas_recentes = (
            Tarefa.query
            .filter(
                Tarefa.op_id == op_id,
                Tarefa.setor_id == setor_id,
                Tarefa.nome == nome,
                Tarefa.prazo == prazo_convertido,
                Tarefa.criada_em >= limite_duplicidade,
            )
            .order_by(Tarefa.criada_em.desc())
            .all()
        )
        for tarefa_recente in tarefas_recentes:
            if ids_responsaveis_tarefa(tarefa_recente) == responsaveis_ids:
                tarefa_duplicada = tarefa_recente
                break

        if tarefa_duplicada:
            flash("Esta ação já foi processada.", "info")
            return redirect(request.referrer or url_for(
                "ver_op",
                id=tarefa_duplicada.op_id,
                setor=setor_id,
                tarefa=tarefa_duplicada.id
            ))

        nova = Tarefa(
            op_id=op_id,
            setor_id=setor_id,
            nome=nome,
            prazo=prazo_convertido,
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

        observacao_entrega = request.form.get("observacao_entrega", "").strip()
        agora = agora_brasilia()
        aplicar_status_tarefa(tarefa, STATUS_EM_VALIDACAO)
        preencher_data_se_vazia(tarefa, "enviada_validacao_em", agora)
        preencher_data_se_vazia(tarefa, "entregue_em", agora)
        tarefa.observacao_entrega = observacao_entrega or None

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

        acesso_negado = exigir_permissao_validacao(tarefa)
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
