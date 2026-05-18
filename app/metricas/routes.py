from flask import Blueprint, render_template

from database.models import OP, Setor, Tarefa


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


def metricas_tarefas(tarefas):
    totais_por_status = {
        status: 0
        for status in STATUS_TAREFAS
    }

    for tarefa in tarefas:
        totais_por_status[status_visual_tarefa(tarefa)] += 1

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


def create_metricas_blueprint(tipos_permitidos):
    metricas_bp = Blueprint("metricas_bp", __name__)

    @metricas_bp.route("/metricas")
    @tipos_permitidos("ADMIN", "ATENDENTE", "PCP")
    def metricas():
        tarefas = Tarefa.query.all()
        setores = Setor.query.order_by(Setor.nome).all()
        ops = OP.query.all()

        tarefas_metricas = metricas_tarefas(tarefas)

        return render_template(
            "metricas/index.html",
            status_tarefas=STATUS_TAREFAS,
            totais_por_status=tarefas_metricas["totais_por_status"],
            tempos=tarefas_metricas["tempos"],
            gargalos=gargalos_por_setor(setores, tarefas),
            ops=metricas_ops(ops),
            formatar_dias=formatar_dias,
        )

    return metricas_bp
