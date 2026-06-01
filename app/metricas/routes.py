import time as perf_time
from datetime import datetime, time, timedelta

from flask import Blueprint, current_app, render_template, request
from sqlalchemy.orm import selectinload

from database.models import OP, Setor, Tarefa, User
from metricas_responsaveis import ranking_metricas_responsaveis
from tempo import hoje_brasilia


STATUS_PENDENTE = "PENDENTE"
STATUS_EM_ANDAMENTO = "EM ANDAMENTO"
STATUS_EM_VALIDACAO = "EM VALIDAÇÃO"
STATUS_ENTREGUE = "ENTREGUE"

STATUS_TAREFAS = [
    STATUS_PENDENTE,
    STATUS_EM_ANDAMENTO,
    STATUS_EM_VALIDACAO,
    STATUS_ENTREGUE,
]

TIPOS_OP_FILTRO = [
    ("todas", "Todas"),
    ("alta_prioridade", "Alta prioridade"),
    ("op_atrasada", "OP atrasada"),
    ("op_urgente", "OP urgente"),
]

PERIODOS_FILTRO = [
    ("todos", "Todos os per\u00edodos"),
    ("7", "\u00daltimos 7 dias"),
    ("30", "\u00daltimos 30 dias"),
    ("mes_atual", "M\u00eas atual"),
    ("personalizado", "Personalizado"),
]


def ids_querystring(nome):
    ids = []
    for valor in request.args.getlist(nome):
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    return ids


def id_querystring(nome):
    try:
        return int(request.args.get(nome, ""))
    except (TypeError, ValueError):
        return None


def data_querystring(nome):
    valor = request.args.get(nome, "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def filtros_metricas():
    status = [
        valor
        for valor in request.args.getlist("status")
        if valor in STATUS_TAREFAS
    ]
    tipo_op = request.args.get("tipo_op", "todas").strip() or "todas"
    tipos_validos = {valor for valor, _rotulo in TIPOS_OP_FILTRO}
    if tipo_op not in tipos_validos:
        tipo_op = "todas"

    periodo = request.args.get("periodo", "todos").strip() or "todos"
    periodos_validos = {valor for valor, _rotulo in PERIODOS_FILTRO}
    if periodo not in periodos_validos:
        periodo = "todos"

    return {
        "setores": ids_querystring("setores"),
        "ops": ids_querystring("ops"),
        "responsaveis": ids_querystring("responsaveis"),
        "status": status,
        "tipo_op": tipo_op,
        "periodo": periodo,
        "data_inicio": data_querystring("data_inicio"),
        "data_fim": data_querystring("data_fim"),
        "cliente": request.args.get("cliente", "").strip(),
    }


def status_visual_tarefa(tarefa):
    if tarefa.validado or tarefa.status == STATUS_ENTREGUE:
        return STATUS_ENTREGUE
    if tarefa.entregue or tarefa.status == STATUS_EM_VALIDACAO:
        return STATUS_EM_VALIDACAO
    if tarefa.status == STATUS_EM_ANDAMENTO:
        return STATUS_EM_ANDAMENTO
    return STATUS_PENDENTE


def diferenca_dias(inicio, fim):
    if not inicio or not fim or fim < inicio:
        return None
    return (fim - inicio).total_seconds() / 86400


def media_dias(valores):
    validos = [valor for valor in valores if valor is not None]
    if not validos:
        return None
    return sum(validos) / len(validos)


def formatar_dias(valor):
    if valor is None:
        return "-"
    if valor < 1:
        horas = valor * 24
        return f"{horas:.1f} h"
    return f"{valor:.1f} dias"


def formatar_percentual(valor):
    if valor is None:
        return "-"
    return f"{valor:.1f}%"


def intervalo_periodo(filtros, hoje):
    periodo = filtros["periodo"]

    if periodo == "7":
        return hoje - timedelta(days=6), hoje
    if periodo == "30":
        return hoje - timedelta(days=29), hoje
    if periodo == "mes_atual":
        return hoje.replace(day=1), hoje
    if periodo == "personalizado":
        inicio = filtros["data_inicio"]
        fim = filtros["data_fim"]
        if inicio and fim and fim < inicio:
            inicio, fim = fim, inicio
        return inicio, fim

    return None, None


def data_no_intervalo(valor, inicio, fim):
    if not inicio and not fim:
        return True
    if not valor:
        return False

    data = valor.date() if hasattr(valor, "date") else valor
    if inicio and data < inicio:
        return False
    if fim and data > fim:
        return False
    return True


def op_atrasada(op, hoje):
    return bool(
        op.prazo_final
        and op.prazo_final < hoje
        and op.status not in ["FINALIZADA", "ARQUIVADA"]
    )


def op_urgente(op, hoje):
    return bool(
        op.prazo_final
        and hoje <= op.prazo_final <= hoje + timedelta(days=2)
        and op.status not in ["FINALIZADA", "ARQUIVADA"]
    )


def op_no_filtro_tipo(op, tipo_op, hoje):
    if tipo_op == "alta_prioridade":
        return bool(op.alta_prioridade)
    if tipo_op == "op_atrasada":
        return op_atrasada(op, hoje)
    if tipo_op == "op_urgente":
        return op_urgente(op, hoje)
    return True


def aplicar_filtros_tarefas(tarefas, filtros, hoje):
    inicio, fim = intervalo_periodo(filtros, hoje)
    tarefas_filtradas = []

    for tarefa in tarefas:
        responsaveis = list(getattr(tarefa, "responsaveis", []) or [])
        if filtros["setores"] and tarefa.setor_id not in filtros["setores"]:
            continue
        if filtros["ops"] and tarefa.op_id not in filtros["ops"]:
            continue
        if filtros["responsaveis"] and not any(
            responsavel.id in filtros["responsaveis"]
            for responsavel in responsaveis
        ):
            continue
        if filtros["status"] and status_visual_tarefa(tarefa) not in filtros["status"]:
            continue
        if tarefa.op and not op_no_filtro_tipo(tarefa.op, filtros["tipo_op"], hoje):
            continue
        if filtros["cliente"]:
            cliente = (getattr(tarefa.op, "cliente", "") or "").lower()
            if filtros["cliente"].lower() not in cliente:
                continue
        if not data_no_intervalo(tarefa.criada_em, inicio, fim):
            continue

        tarefas_filtradas.append(tarefa)

    return tarefas_filtradas


def aplicar_filtros_ops(ops, filtros, hoje):
    inicio, fim = intervalo_periodo(filtros, hoje)
    ops_filtradas = []

    for op in ops:
        if filtros["ops"] and op.id not in filtros["ops"]:
            continue
        if not op_no_filtro_tipo(op, filtros["tipo_op"], hoje):
            continue
        if filtros["cliente"] and filtros["cliente"].lower() not in (op.cliente or "").lower():
            continue
        if not data_no_intervalo(op.criada_em, inicio, fim):
            continue
        ops_filtradas.append(op)

    return ops_filtradas


def metricas_tarefas(tarefas, hoje):
    totais_por_status = {
        status: 0
        for status in STATUS_TAREFAS
    }
    atrasadas = 0
    recusadas = 0

    for tarefa in tarefas:
        totais_por_status[status_visual_tarefa(tarefa)] += 1
        if tarefa.prazo and tarefa.prazo < hoje and not tarefa_concluida(tarefa):
            atrasadas += 1
        if tarefa_recusada(tarefa):
            recusadas += 1

    total_tarefas = len(tarefas)
    resumo = {
        "total": total_tarefas,
        "pendentes": totais_por_status[STATUS_PENDENTE],
        "em_andamento": totais_por_status[STATUS_EM_ANDAMENTO],
        "entregues": totais_por_status[STATUS_EM_VALIDACAO],
        "concluidas": totais_por_status[STATUS_ENTREGUE],
        "atrasadas": atrasadas,
        "recusadas": recusadas,
        "taxa_atraso": (atrasadas / total_tarefas * 100) if total_tarefas else 0.0,
        "taxa_recusa": (recusadas / total_tarefas * 100) if total_tarefas else 0.0,
    }

    tempos = {
        "ate_iniciar": media_dias(
            diferenca_dias(tarefa.criada_em, tarefa.iniciada_em)
            for tarefa in tarefas
        ),
        "em_producao": media_dias(
            diferenca_dias(tarefa.iniciada_em, tarefa.enviada_validacao_em)
            for tarefa in tarefas
        ),
        "aguardando_validacao": media_dias(
            diferenca_dias(tarefa.enviada_validacao_em, tarefa.validada_em)
            for tarefa in tarefas
        ),
        "total": media_dias(
            diferenca_dias(tarefa.criada_em, tarefa.concluida_em)
            for tarefa in tarefas
        ),
    }

    return {
        "resumo": resumo,
        "totais_por_status": totais_por_status,
        "tempos": tempos,
    }


def gargalos_por_setor(setores, tarefas):
    linhas = []

    for setor in setores:
        tarefas_setor = [
            tarefa
            for tarefa in tarefas
            if tarefa.setor_id == setor.id
        ]

        contagens = {
            status: 0
            for status in STATUS_TAREFAS
        }
        for tarefa in tarefas_setor:
            contagens[status_visual_tarefa(tarefa)] += 1

        media_producao = media_dias(
            diferenca_dias(tarefa.iniciada_em, tarefa.enviada_validacao_em)
            for tarefa in tarefas_setor
        )

        linhas.append({
            "setor": setor,
            "pendentes": contagens[STATUS_PENDENTE],
            "em_andamento": contagens[STATUS_EM_ANDAMENTO],
            "em_validacao": contagens[STATUS_EM_VALIDACAO],
            "entregues": contagens[STATUS_ENTREGUE],
            "total": len(tarefas_setor),
            "media_producao": media_producao,
        })

    linhas.sort(
        key=lambda linha: (
            -linha["pendentes"],
            -linha["em_andamento"],
            -linha["em_validacao"],
            linha["setor"].nome,
        )
    )
    return linhas


def ranking_setores_pendentes(gargalos):
    return [
        linha
        for linha in gargalos
        if linha["pendentes"] > 0
    ]


def ranking_setores_producao(gargalos):
    linhas = [
        linha
        for linha in gargalos
        if linha["media_producao"] is not None
    ]
    linhas.sort(
        key=lambda linha: (
            -linha["media_producao"],
            linha["setor"].nome,
        )
    )
    return linhas


def dias_op_aberta(op, agora):
    if not op.criada_em:
        return None
    fim = op.finalizada_em or agora
    return diferenca_dias(op.criada_em, fim)


def ranking_ops_abertas(ops, agora):
    linhas = []

    for op in ops:
        if op.status in ["FINALIZADA", "ARQUIVADA"]:
            continue
        tempo_aberta = dias_op_aberta(op, agora)
        if tempo_aberta is None:
            continue
        linhas.append({
            "op": op,
            "tempo_aberta": tempo_aberta,
        })

    linhas.sort(
        key=lambda linha: (
            -linha["tempo_aberta"],
            linha["op"].nome,
        )
    )
    return linhas


def op_nao_arquivada(op):
    return bool(op and op.status != "ARQUIVADA" and not op.arquivada_em)


def tarefas_ops_nao_arquivadas(tarefas):
    return [
        tarefa
        for tarefa in tarefas
        if op_nao_arquivada(tarefa.op)
    ]


def fim_tarefa(tarefa):
    return tarefa.concluida_em or tarefa.validada_em


def inicio_tarefa(tarefa, usar_criacao_como_fallback=False):
    if tarefa.iniciada_em:
        return tarefa.iniciada_em
    if usar_criacao_como_fallback:
        return tarefa.criada_em
    return None


def tempo_conclusao_tarefa(tarefa, usar_criacao_como_fallback=False):
    return diferenca_dias(
        inicio_tarefa(tarefa, usar_criacao_como_fallback),
        fim_tarefa(tarefa),
    )


def tarefa_concluida(tarefa):
    return bool(
        fim_tarefa(tarefa)
        or tarefa.validado
        or tarefa.status == STATUS_ENTREGUE
    )


def tarefa_recusada(tarefa):
    return bool(tarefa.recusada_em or tarefa.motivo_recusa)


def ranking_setores_tempo_conclusao(
    setores,
    tarefas,
    mais_rapidos=False,
    usar_criacao_como_fallback=True,
):
    linhas = []

    for setor in setores:
        tempos = [
            tempo
            for tempo in (
                tempo_conclusao_tarefa(
                    tarefa,
                    usar_criacao_como_fallback=usar_criacao_como_fallback,
                )
                for tarefa in tarefas
                if tarefa.setor_id == setor.id
            )
            if tempo is not None
        ]

        if not tempos:
            continue

        linhas.append({
            "setor": setor,
            "media": media_dias(tempos),
            "quantidade": len(tempos),
            "maior_atraso": max(tempos),
        })

    linhas.sort(
        key=lambda linha: (
            linha["media"] if mais_rapidos else -linha["media"],
            linha["setor"].nome,
        )
    )
    return linhas


def ranking_setores_recusadas(setores, tarefas):
    linhas = []

    for setor in setores:
        total = sum(
            1
            for tarefa in tarefas
            if tarefa.setor_id == setor.id and tarefa_recusada(tarefa)
        )
        if total:
            linhas.append({
                "setor": setor,
                "total": total,
            })

    linhas.sort(key=lambda linha: (-linha["total"], linha["setor"].nome))
    return linhas


def ranking_setores_concluidas(setores, tarefas):
    linhas = []

    for setor in setores:
        total = sum(
            1
            for tarefa in tarefas
            if tarefa.setor_id == setor.id and tarefa_concluida(tarefa)
        )
        if total:
            linhas.append({
                "setor": setor,
                "total": total,
            })

    linhas.sort(key=lambda linha: (-linha["total"], linha["setor"].nome))
    return linhas


def ranking_tarefas_demoradas(tarefas):
    linhas = []

    for tarefa in tarefas:
        tempo = tempo_conclusao_tarefa(tarefa, usar_criacao_como_fallback=True)
        if tempo is None:
            continue
        linhas.append({
            "tarefa": tarefa,
            "tempo": tempo,
        })

    linhas.sort(
        key=lambda linha: (
            -linha["tempo"],
            linha["tarefa"].op.nome if linha["tarefa"].op else "",
            linha["tarefa"].nome,
        )
    )
    return linhas


def filtros_restringem_tarefas(filtros):
    return bool(
        filtros["setores"]
        or filtros["responsaveis"]
        or filtros["status"]
        or filtros["cliente"]
        or filtros["periodo"] != "todos"
    )


def metricas_ops(ops):
    tempos_conclusao = (
        diferenca_dias(op.criada_em, op.finalizada_em)
        for op in ops
    )

    return {
        "em_andamento": sum(1 for op in ops if op.status == "EM ANDAMENTO"),
        "finalizadas": sum(1 for op in ops if op.status == "FINALIZADA"),
        "tempo_medio_conclusao": media_dias(tempos_conclusao),
    }


def grafico_status(totais_por_status):
    return {
        "labels": list(totais_por_status.keys()),
        "data": list(totais_por_status.values()),
    }


def grafico_setores(gargalos):
    linhas = [
        linha
        for linha in gargalos
        if linha["total"] > 0
    ]
    return {
        "labels": [linha["setor"].nome for linha in linhas],
        "data": [linha["total"] for linha in linhas],
    }


def grafico_tempos(tempos):
    etapas = [
        ("Até iniciar", tempos["ate_iniciar"]),
        ("Em produção", tempos["em_producao"]),
        ("Aguardando validação", tempos["aguardando_validacao"]),
        ("Total", tempos["total"]),
    ]
    etapas_com_dados = [
        (rotulo, valor)
        for rotulo, valor in etapas
        if valor is not None
    ]
    return {
        "labels": [rotulo for rotulo, _valor in etapas_com_dados],
        "data": [round(valor, 2) for _rotulo, valor in etapas_com_dados],
    }


def formatar_data(valor):
    if not valor:
        return "-"
    return valor.strftime("%d/%m/%Y")


def formatar_data_hora(valor):
    if not valor:
        return "-"
    return valor.strftime("%d/%m/%Y %H:%M")


def tarefas_para_analise(tarefas):
    return sorted(
        tarefas,
        key=lambda tarefa: (
            tarefa.op.nome if tarefa.op else "",
            tarefa.nome,
            tarefa.id,
        )
    )


def analise_tarefa(tarefa):
    if not tarefa:
        return None

    fim_tarefa = tarefa.concluida_em or tarefa.validada_em

    return {
        "tarefa": tarefa,
        "status": status_visual_tarefa(tarefa),
        "validada_concluida_em": fim_tarefa,
        "tempo_ate_iniciar": diferenca_dias(tarefa.criada_em, tarefa.iniciada_em),
        "tempo_em_producao": diferenca_dias(tarefa.iniciada_em, tarefa.enviada_validacao_em),
        "tempo_aguardando_validacao": diferenca_dias(tarefa.enviada_validacao_em, fim_tarefa),
        "tempo_total": diferenca_dias(tarefa.criada_em, fim_tarefa),
    }


def create_metricas_blueprint(tipos_permitidos):
    metricas_bp = Blueprint("metricas_bp", __name__)

    @metricas_bp.route("/metricas")
    @tipos_permitidos("ADMIN", "ATENDENTE", "PCP")
    def metricas():
        inicio_metricas = perf_time.perf_counter()
        hoje = hoje_brasilia()
        agora = datetime.combine(hoje, time.max)
        filtros = filtros_metricas()
        tarefa_id = id_querystring("tarefa_id")

        tarefas = (
            Tarefa.query
            .options(
                selectinload(Tarefa.op),
                selectinload(Tarefa.setor),
                selectinload(Tarefa.responsaveis).selectinload(User.setor),
            )
            .all()
        )
        setores = Setor.query.order_by(Setor.nome).all()
        ops = OP.query.all()
        usuarios_disponiveis = sorted(
            User.query.filter(User.ativo.is_(True), User.setor_id.isnot(None)).all(),
            key=lambda usuario: ((usuario.nome or usuario.email or "").lower(), usuario.id),
        )

        tarefas = aplicar_filtros_tarefas(tarefas, filtros, hoje)
        ops_filtradas = aplicar_filtros_ops(ops, filtros, hoje)
        if filtros_restringem_tarefas(filtros):
            op_ids_tarefas = {tarefa.op_id for tarefa in tarefas}
            ops_filtradas = [
                op
                for op in ops_filtradas
                if op.id in op_ids_tarefas
            ]

        tarefas_metricas = metricas_tarefas(tarefas, hoje)
        gargalos = gargalos_por_setor(setores, tarefas)
        metricas_responsaveis = ranking_metricas_responsaveis(tarefas, hoje)
        tarefas_rankings = tarefas_ops_nao_arquivadas(tarefas)
        tarefas_opcoes = tarefas_para_analise(tarefas)
        tarefa_selecionada = next(
            (tarefa for tarefa in tarefas_opcoes if tarefa.id == tarefa_id),
            None
        )

        resposta = render_template(
            "metricas/index.html",
            status_tarefas=STATUS_TAREFAS,
            tipos_op_filtro=TIPOS_OP_FILTRO,
            periodos_filtro=PERIODOS_FILTRO,
            filtros=filtros,
            setores_disponiveis=setores,
            usuarios_disponiveis=usuarios_disponiveis,
            ops_disponiveis=OP.query.order_by(OP.nome).all(),
            resumo_tarefas=tarefas_metricas["resumo"],
            totais_por_status=tarefas_metricas["totais_por_status"],
            tempos=tarefas_metricas["tempos"],
            gargalos=gargalos,
            ranking_pendentes=ranking_setores_pendentes(gargalos),
            ranking_producao=ranking_setores_producao(gargalos),
            ranking_ops=ranking_ops_abertas(ops_filtradas, agora),
            ranking_setores_rapidos=ranking_setores_tempo_conclusao(
                setores,
                tarefas_rankings,
                mais_rapidos=True,
                usar_criacao_como_fallback=False,
            ),
            ranking_setores_gargalo=ranking_setores_tempo_conclusao(
                setores,
                tarefas_rankings,
            ),
            ranking_setores_recusadas=ranking_setores_recusadas(setores, tarefas_rankings),
            ranking_setores_concluidas=ranking_setores_concluidas(setores, tarefas_rankings),
            ranking_responsaveis=metricas_responsaveis["usuarios"],
            geral_setor_responsaveis=metricas_responsaveis["geral_setor"],
            metricas_responsaveis=metricas_responsaveis,
            ranking_tarefas_demoradas=ranking_tarefas_demoradas(tarefas_rankings),
            ops=metricas_ops(ops_filtradas),
            graficos={
                "status": grafico_status(tarefas_metricas["totais_por_status"]),
                "setores": grafico_setores(gargalos),
                "tempos": grafico_tempos(tarefas_metricas["tempos"]),
            },
            tarefas_opcoes=tarefas_opcoes,
            tarefa_selecionada_id=tarefa_id,
            analise_tarefa=analise_tarefa(tarefa_selecionada),
            formatar_dias=formatar_dias,
            formatar_percentual=formatar_percentual,
            formatar_data=formatar_data,
            formatar_data_hora=formatar_data_hora,
        )
        current_app.logger.info(
            "metricas_timing tarefas=%s ops=%s total_ms=%.1f",
            len(tarefas),
            len(ops_filtradas),
            (perf_time.perf_counter() - inicio_metricas) * 1000,
        )
        return resposta

    return metricas_bp
