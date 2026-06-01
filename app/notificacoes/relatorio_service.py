from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
import os

from flask import current_app, has_app_context, has_request_context, request
from sqlalchemy.orm import selectinload

from database.models import db, NotificationEmailDelivery, OP, Tarefa, User
from email_service import configuracao_email, enviar_email, parse_bool, smtp_configurado
from tempo import agora_brasilia, hoje_brasilia


JANELAS_VALIDAS = {"10h", "15h"}
REPORT_TYPE = "relatorio_operacional"
STATUS_FINALIZADOS = ("FINALIZADA", "ARQUIVADA")
STATUS_EM_ESPERA = "EM ESPERA"
STATUS_EMAIL_ENVIADO = "enviado"
STATUS_EMAIL_PULOU = "pulou"
STATUS_EMAIL_ERRO = "erro"

SECOES = (
    ("ops_atrasadas", "OPs atrasadas"),
    ("ops_urgentes", "OPs urgentes"),
    ("ops_proximas", "OPs proximas do prazo"),
    ("tarefas_atrasadas", "Tarefas atrasadas"),
    ("tarefas_hoje", "Tarefas para hoje"),
    ("tarefas_proximas", "Tarefas proximas do prazo"),
    ("tarefas_sem_prazo", "Tarefas sem prazo"),
    ("tarefas_sem_responsavel", "Tarefas sem responsavel especifico"),
    ("tarefas_atribuidas", "Tarefas atribuidas diretamente a voce"),
    ("tarefas_aguardando_acao", "Tarefas aguardando acao do setor"),
    ("aguardando_validacao", "Aguardando validacao"),
    ("pendencias_planejamento", "Pendencias de planejamento"),
)


@dataclass(frozen=True)
class RelatorioItem:
    chave: str
    texto: str
    link: str
    prazo: object = None


@dataclass
class RelatorioUsuario:
    usuario: User
    janela: str
    data_operacional: object
    secoes: dict[str, list[RelatorioItem]] = field(
        default_factory=lambda: {chave: [] for chave, _titulo in SECOES}
    )

    def tem_pendencias(self):
        return any(self.secoes[chave] for chave, _titulo in SECOES)

    def resumo_conteudo(self):
        partes = [
            f"{titulo}: {len(self.secoes[chave])}"
            for chave, titulo in SECOES
            if self.secoes[chave]
        ]
        return "; ".join(partes)[:500]


def validar_janela(janela):
    janela = (janela or "").strip().lower()
    if janela not in JANELAS_VALIDAS:
        raise ValueError("Janela invalida. Use 10h ou 15h.")
    return janela


def emails_operacionais_ativos():
    chaves = ("EMAILS_OPERACIONAIS_ATIVOS", "ENVIAR_EMAILS_OPERACIONAIS")
    if has_app_context():
        for chave in chaves:
            valor = current_app.config.get(chave)
            if valor not in (None, ""):
                return parse_bool(valor, default=False)

    for chave in chaves:
        valor = os.environ.get(chave)
        if valor not in (None, ""):
            return parse_bool(valor, default=False)

    return False


def motivo_envio_bloqueado():
    config = configuracao_email()
    if not config.enabled:
        return "MAIL_ENABLED=false"
    if not emails_operacionais_ativos():
        return "EMAILS_OPERACIONAIS_ATIVOS=false"
    if not config.configurado:
        return "SMTP incompleto: " + ", ".join(config.missing)
    return None


def envio_real_ativo():
    return motivo_envio_bloqueado() is None and smtp_configurado()


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


def formatar_data(valor):
    if not valor:
        return "sem prazo"
    return valor.strftime("%d/%m")


def cliente_op(op):
    cliente = (getattr(op, "cliente", None) or "").strip()
    return cliente or "Cliente nao informado"


def link_op(op):
    return f"/op/{op.id}"


def link_tarefa(tarefa):
    return f"/op/{tarefa.op_id}?setor={tarefa.setor_id}&tarefa={tarefa.id}"


def op_ativa(op):
    return op and op.status not in STATUS_FINALIZADOS


def tarefa_aberta(tarefa):
    return (
        tarefa
        and not tarefa.validado
        and not tarefa.em_espera
        and tarefa.status != STATUS_EM_ESPERA
        and op_ativa(tarefa.op)
    )


def tarefa_aguarda_acao_setor(tarefa):
    return tarefa_aberta(tarefa) and not tarefa.entregue


def responsaveis_ativos(tarefa):
    return sorted(
        [usuario for usuario in (tarefa.responsaveis or []) if usuario.ativo],
        key=lambda usuario: ((usuario.nome or usuario.email or "").casefold(), usuario.id),
    )


def tarefa_sem_responsavel(tarefa):
    return not responsaveis_ativos(tarefa)


def tarefa_pertence_ao_usuario_setor(tarefa, usuario):
    if usuario.tipo != "SETOR" or not usuario.setor_id:
        return False

    responsaveis = responsaveis_ativos(tarefa)
    if responsaveis:
        return any(responsavel.id == usuario.id for responsavel in responsaveis)

    return tarefa.setor_id == usuario.setor_id


def tarefa_atribuida_ao_usuario(tarefa, usuario):
    return any(responsavel.id == usuario.id for responsavel in responsaveis_ativos(tarefa))


def texto_op(op, prefixo_prazo):
    return f"OP {op.id} - {cliente_op(op)} - {op.nome} - {prefixo_prazo}"


def texto_tarefa(tarefa, prefixo_prazo):
    setor = tarefa.setor.nome if tarefa.setor else "Setor nao informado"
    return (
        f"OP {tarefa.op.id} - {cliente_op(tarefa.op)} - "
        f"Setor {setor} - {tarefa.nome} - {prefixo_prazo}"
    )


def adicionar_item(relatorio, secao, item):
    existentes = {existente.chave for existente in relatorio.secoes[secao]}
    if item.chave not in existentes:
        relatorio.secoes[secao].append(item)


def item_op(op, descricao):
    return RelatorioItem(
        chave=f"op:{op.id}:{descricao}",
        texto=texto_op(op, descricao),
        link=link_op(op),
        prazo=op.prazo_final,
    )


def item_tarefa(tarefa, descricao):
    return RelatorioItem(
        chave=f"tarefa:{tarefa.id}:{descricao}",
        texto=texto_tarefa(tarefa, descricao),
        link=link_tarefa(tarefa),
        prazo=tarefa.prazo,
    )


def ordenar_relatorio(relatorio):
    for chave, _titulo in SECOES:
        relatorio.secoes[chave].sort(
            key=lambda item: (
                item.prazo is None,
                item.prazo or relatorio.data_operacional,
                item.texto.casefold(),
            )
        )


def carregar_ops_ativas():
    return (
        OP.query
        .options(selectinload(OP.tarefas).selectinload(Tarefa.setor))
        .filter(OP.status.notin_(STATUS_FINALIZADOS))
        .all()
    )


def carregar_tarefas_ativas():
    return (
        Tarefa.query
        .options(
            selectinload(Tarefa.op),
            selectinload(Tarefa.setor),
            selectinload(Tarefa.responsaveis),
        )
        .join(OP)
        .filter(
            OP.status.notin_(STATUS_FINALIZADOS),
            Tarefa.validado.is_(False),
            Tarefa.em_espera.is_(False),
            Tarefa.status != STATUS_EM_ESPERA,
        )
        .all()
    )


def carregar_usuarios_ativos():
    return (
        User.query
        .options(selectinload(User.setor))
        .filter(User.ativo.is_(True))
        .order_by(User.id)
        .all()
    )


def usuario_recebe_relatorio(usuario):
    return usuario.tipo in {"ATENDENTE", "PCP", "SETOR"}


def atendente_responsavel_op(usuario, op):
    return (op.atendente or "").strip().lower() == (usuario.email or "").strip().lower()


def preencher_ops(relatorio, ops, hoje, proximos_dias, apenas_atendente=False):
    for op in ops:
        if apenas_atendente and not atendente_responsavel_op(relatorio.usuario, op):
            continue

        if op.prazo_final and op.prazo_final < hoje:
            adicionar_item(
                relatorio,
                "ops_atrasadas",
                item_op(op, f"vencida em {formatar_data(op.prazo_final)}"),
            )
        if op.alta_prioridade:
            adicionar_item(
                relatorio,
                "ops_urgentes",
                item_op(op, "alta prioridade"),
            )
        if op.prazo_final and hoje <= op.prazo_final <= proximos_dias:
            adicionar_item(
                relatorio,
                "ops_proximas",
                item_op(op, f"vence em {formatar_data(op.prazo_final)}"),
            )


def preencher_tarefa_por_prazo(relatorio, tarefa, hoje, proximos_dias):
    if tarefa.prazo and tarefa.prazo < hoje:
        adicionar_item(
            relatorio,
            "tarefas_atrasadas",
            item_tarefa(tarefa, f"vencida em {formatar_data(tarefa.prazo)}"),
        )
    elif tarefa.prazo == hoje:
        adicionar_item(
            relatorio,
            "tarefas_hoje",
            item_tarefa(tarefa, "vence hoje"),
        )
    elif tarefa.prazo and hoje < tarefa.prazo <= proximos_dias:
        adicionar_item(
            relatorio,
            "tarefas_proximas",
            item_tarefa(tarefa, f"vence em {formatar_data(tarefa.prazo)}"),
        )
    elif tarefa.prazo is None:
        adicionar_item(
            relatorio,
            "tarefas_sem_prazo",
            item_tarefa(tarefa, "sem prazo definido"),
        )


def preencher_tarefas_setor(relatorio, tarefas, hoje, proximos_dias):
    for tarefa in tarefas:
        if not tarefa_pertence_ao_usuario_setor(tarefa, relatorio.usuario):
            continue

        if tarefa_aguarda_acao_setor(tarefa):
            preencher_tarefa_por_prazo(relatorio, tarefa, hoje, proximos_dias)
            adicionar_item(
                relatorio,
                "tarefas_aguardando_acao",
                item_tarefa(tarefa, "aguardando acao do setor"),
            )
            if tarefa_sem_responsavel(tarefa):
                adicionar_item(
                    relatorio,
                    "tarefas_sem_responsavel",
                    item_tarefa(tarefa, "geral do setor"),
                )
            if tarefa_atribuida_ao_usuario(tarefa, relatorio.usuario):
                adicionar_item(
                    relatorio,
                    "tarefas_atribuidas",
                    item_tarefa(tarefa, "atribuida a voce"),
                )


def preencher_tarefas_visao_ampla(relatorio, tarefas, hoje, proximos_dias):
    for tarefa in tarefas:
        preencher_tarefa_por_prazo(relatorio, tarefa, hoje, proximos_dias)
        if tarefa.entregue and not tarefa.validado:
            adicionar_item(
                relatorio,
                "aguardando_validacao",
                item_tarefa(tarefa, "entregue aguardando validacao"),
            )


def preencher_tarefas_atendente(relatorio, tarefas, hoje, proximos_dias):
    for tarefa in tarefas:
        if not atendente_responsavel_op(relatorio.usuario, tarefa.op):
            continue
        preencher_tarefa_por_prazo(relatorio, tarefa, hoje, proximos_dias)
        if tarefa.entregue and not tarefa.validado:
            adicionar_item(
                relatorio,
                "aguardando_validacao",
                item_tarefa(tarefa, "entregue aguardando validacao"),
            )


def preencher_pendencias_planejamento(relatorio, ops):
    for op in ops:
        if not op.tarefas:
            adicionar_item(
                relatorio,
                "pendencias_planejamento",
                item_op(op, "sem tarefas planejadas"),
            )


def montar_relatorio_usuario(usuario, janela, data_operacional=None, ops=None, tarefas=None):
    janela = validar_janela(janela)
    hoje = data_operacional or hoje_brasilia()
    proximos_dias = hoje + timedelta(days=2)
    ops = ops if ops is not None else carregar_ops_ativas()
    tarefas = tarefas if tarefas is not None else carregar_tarefas_ativas()

    relatorio = RelatorioUsuario(
        usuario=usuario,
        janela=janela,
        data_operacional=hoje,
    )

    if usuario.tipo == "ATENDENTE":
        preencher_ops(relatorio, ops, hoje, proximos_dias, apenas_atendente=True)
        preencher_tarefas_atendente(relatorio, tarefas, hoje, proximos_dias)
    elif usuario.tipo == "PCP":
        preencher_ops(relatorio, ops, hoje, proximos_dias)
        preencher_tarefas_visao_ampla(relatorio, tarefas, hoje, proximos_dias)
        preencher_pendencias_planejamento(relatorio, ops)
    elif usuario.tipo == "SETOR":
        preencher_tarefas_setor(relatorio, tarefas, hoje, proximos_dias)

    ordenar_relatorio(relatorio)
    return relatorio


def montar_relatorios(janela, data_operacional=None):
    janela = validar_janela(janela)
    hoje = data_operacional or hoje_brasilia()
    ops = carregar_ops_ativas()
    tarefas = carregar_tarefas_ativas()
    relatorios = []

    for usuario in carregar_usuarios_ativos():
        if not usuario_recebe_relatorio(usuario):
            continue
        relatorios.append(
            montar_relatorio_usuario(
                usuario,
                janela,
                data_operacional=hoje,
                ops=ops,
                tarefas=tarefas,
            )
        )

    return relatorios


def renderizar_texto(relatorio):
    nome = relatorio.usuario.nome or relatorio.usuario.email
    linhas = [
        f"Ola, {nome}!",
        "",
        "Segue seu resumo operacional do sistema:",
        "",
    ]

    for chave, titulo in SECOES:
        itens = relatorio.secoes[chave]
        if not itens:
            continue
        linhas.append(f"{titulo}:")
        for item in itens:
            linhas.append(f"* {item.texto}")
        linhas.append("")

    linhas.extend([
        "Acesse o sistema para acompanhar os detalhes.",
        "",
        "Atenciosamente,",
        "Prospera Producoes",
    ])
    return "\n".join(linhas)


def renderizar_html(relatorio):
    return current_app.jinja_env.get_template(
        "email/relatorio_operacional.html"
    ).render(
        relatorio=relatorio,
        secoes=SECOES,
        url_absoluta=url_absoluta,
    )


def hash_conteudo(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def entrega_enviada_existente(relatorio):
    return NotificationEmailDelivery.query.filter_by(
        report_type=REPORT_TYPE,
        user_id=relatorio.usuario.id,
        janela=relatorio.janela,
        data_operacional=relatorio.data_operacional,
        status=STATUS_EMAIL_ENVIADO,
    ).first()


def registrar_entrega(relatorio, status, content_hash=None, erro=None, content_summary=None):
    entrega = NotificationEmailDelivery(
        report_type=REPORT_TYPE,
        user_id=relatorio.usuario.id,
        recipient_email=(relatorio.usuario.email or "").strip().lower(),
        janela=relatorio.janela,
        data_operacional=relatorio.data_operacional,
        content_hash=content_hash,
        content_summary=content_summary,
        status=status,
        erro=(erro or None),
        created_at=agora_brasilia(),
        sent_at=agora_brasilia() if status == STATUS_EMAIL_ENVIADO else None,
    )
    db.session.add(entrega)
    return entrega


def assunto_relatorio(janela):
    return f"Relatorio operacional - {janela} - Prospera Producoes"


def enviar_relatorio_usuario(relatorio):
    if not relatorio.tem_pendencias():
        registrar_entrega(
            relatorio,
            STATUS_EMAIL_PULOU,
            erro="sem_pendencias",
            content_summary="sem pendencias",
        )
        return "sem_pendencias"

    texto = renderizar_texto(relatorio)
    content_hash = hash_conteudo(texto)
    content_summary = relatorio.resumo_conteudo()

    if entrega_enviada_existente(relatorio):
        registrar_entrega(
            relatorio,
            STATUS_EMAIL_PULOU,
            content_hash=content_hash,
            erro="duplicado",
            content_summary=content_summary,
        )
        return "duplicado"

    motivo_bloqueio = motivo_envio_bloqueado()
    if motivo_bloqueio:
        current_app.logger.info(
            "relatorio_operacional_email_nao_enviado usuario_id=%s motivo=%s",
            relatorio.usuario.id,
            motivo_bloqueio,
        )
        registrar_entrega(
            relatorio,
            STATUS_EMAIL_PULOU,
            content_hash=content_hash,
            erro=motivo_bloqueio,
            content_summary=content_summary,
        )
        return "pulou"

    destinatario = (relatorio.usuario.email or "").strip().lower()
    html = renderizar_html(relatorio)
    resultado = enviar_email(
        [destinatario],
        assunto_relatorio(relatorio.janela),
        texto,
        html=html,
    )

    if resultado.enviado:
        registrar_entrega(
            relatorio,
            STATUS_EMAIL_ENVIADO,
            content_hash=content_hash,
            content_summary=content_summary,
        )
        return "enviado"

    erro = resultado.erro or "email_nao_enviado"
    current_app.logger.error(
        "relatorio_operacional_email_erro usuario_id=%s erro=%s",
        relatorio.usuario.id,
        erro,
    )
    registrar_entrega(
        relatorio,
        STATUS_EMAIL_ERRO,
        content_hash=content_hash,
        erro=erro[:500],
        content_summary=content_summary,
    )
    return "erro"


def resumo_vazio(janela, data_operacional):
    return {
        "janela": janela,
        "data_operacional": data_operacional,
        "usuarios_avaliados": 0,
        "relatorios_com_pendencias": 0,
        "enviados": 0,
        "pulados": 0,
        "erros": 0,
        "duplicados": 0,
        "sem_pendencias": 0,
    }


def enviar_relatorios_operacionais(janela, data_operacional=None):
    janela = validar_janela(janela)
    hoje = data_operacional or hoje_brasilia()
    resumo = resumo_vazio(janela, hoje)

    for relatorio in montar_relatorios(janela, data_operacional=hoje):
        resumo["usuarios_avaliados"] += 1
        if relatorio.tem_pendencias():
            resumo["relatorios_com_pendencias"] += 1

        resultado = enviar_relatorio_usuario(relatorio)
        if resultado == "enviado":
            resumo["enviados"] += 1
        elif resultado == "erro":
            resumo["erros"] += 1
        elif resultado == "duplicado":
            resumo["duplicados"] += 1
            resumo["pulados"] += 1
        elif resultado == "sem_pendencias":
            resumo["sem_pendencias"] += 1
            resumo["pulados"] += 1
        else:
            resumo["pulados"] += 1

    db.session.commit()
    return resumo
