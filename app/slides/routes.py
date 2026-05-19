from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, url_for
from sqlalchemy.orm import selectinload

from database.models import OP, Tarefa


SLIDE_ITEM_LIMIT = 8
SETOR_ITEM_LIMIT = 6


def status_visual_tarefa(tarefa):
    if tarefa.validado:
        return "ENTREGUE"
    if tarefa.entregue:
        return "EM VALIDACAO"
    return tarefa.status or "PENDENTE"


def urgencia_tarefa(tarefa, hoje):
    if not tarefa.prazo:
        return "sem_prazo"
    if tarefa.prazo < hoje:
        return "atrasada"
    if tarefa.prazo == hoje:
        return "hoje"
    if tarefa.prazo == hoje + timedelta(days=1):
        return "amanha"
    if tarefa.prazo <= hoje + timedelta(days=15):
        return "proximos_15_dias"
    return "futura"


def texto_urgencia(urgencia):
    textos = {
        "atrasada": "Atrasada",
        "hoje": "Entrega hoje",
        "amanha": "Entrega amanha",
        "proximos_15_dias": "Proximos 15 dias",
        "futura": "Futura",
        "sem_prazo": "Sem prazo",
    }
    return textos.get(urgencia, "Sem classificacao")


def data_iso(valor):
    return valor.isoformat() if valor else None


def data_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else "Sem prazo"


def item_tarefa(tarefa, hoje):
    urgencia = urgencia_tarefa(tarefa, hoje)
    op = tarefa.op
    setor = tarefa.setor

    return {
        "id": tarefa.id,
        "op_id": tarefa.op_id,
        "op": op.nome if op else "",
        "cliente": getattr(op, "cliente", None) or "Nao informado",
        "tarefa": tarefa.nome,
        "setor": setor.nome if setor else "",
        "prazo": data_iso(tarefa.prazo),
        "prazo_formatado": data_br(tarefa.prazo),
        "status": status_visual_tarefa(tarefa),
        "urgencia": urgencia,
        "urgencia_texto": texto_urgencia(urgencia),
        "alta_prioridade": bool(getattr(op, "alta_prioridade", False)),
        "link": url_for("ver_op", id=tarefa.op_id),
    }


def ordenar_tarefas(tarefa):
    prazo_ordem = tarefa.prazo or date.max
    prioridade = 0 if getattr(tarefa.op, "alta_prioridade", False) else 1
    return (prazo_ordem, prioridade, tarefa.op.nome if tarefa.op else "", tarefa.id)


def tarefas_ativas():
    return (
        Tarefa.query
        .options(
            selectinload(Tarefa.op),
            selectinload(Tarefa.setor),
        )
        .join(OP, Tarefa.op_id == OP.id)
        .filter(
            OP.status.notin_(["FINALIZADA", "ARQUIVADA"]),
            Tarefa.validado.is_(False),
        )
        .all()
    )


def limitar_itens(tarefas, hoje, limite):
    return [
        item_tarefa(tarefa, hoje)
        for tarefa in sorted(tarefas, key=ordenar_tarefas)[:limite]
    ]


def montar_payload_slides():
    hoje = date.today()
    amanha = hoje + timedelta(days=1)
    limite_15 = hoje + timedelta(days=15)
    tarefas = tarefas_ativas()

    atrasadas = [t for t in tarefas if t.prazo and t.prazo < hoje]
    hoje_lista = [t for t in tarefas if t.prazo == hoje]
    amanha_lista = [t for t in tarefas if t.prazo == amanha]
    proximos_15 = [
        t for t in tarefas
        if t.prazo and amanha < t.prazo <= limite_15
    ]

    setores = {}
    for tarefa in tarefas:
        nome_setor = tarefa.setor.nome if tarefa.setor else "Sem setor"
        setores.setdefault(nome_setor, []).append(tarefa)

    slides_setores = [
        {
            "id": f"setor-{nome_setor.lower().replace(' ', '-')}",
            "titulo": nome_setor,
            "vazio": f"Nenhuma tarefa em {nome_setor}",
            "itens": limitar_itens(tarefas_setor, hoje, SETOR_ITEM_LIMIT),
        }
        for nome_setor, tarefas_setor in sorted(setores.items())
    ]

    return {
        "atualizado_em": date.today().isoformat(),
        "intervalos": {
            "atualizacao_ms": 45000,
            "slide_ms": 10000,
        },
        "resumo": {
            "total_atrasadas": len(atrasadas),
            "vencem_hoje": len(hoje_lista),
            "vencem_amanha": len(amanha_lista),
            "proximas_2_semanas": len(proximos_15),
        },
        "categorias": {
            "atrasadas": limitar_itens(atrasadas, hoje, SLIDE_ITEM_LIMIT),
            "hoje": limitar_itens(hoje_lista, hoje, SLIDE_ITEM_LIMIT),
            "amanha": limitar_itens(amanha_lista, hoje, SLIDE_ITEM_LIMIT),
            "proximos_15_dias": limitar_itens(proximos_15, hoje, SLIDE_ITEM_LIMIT),
        },
        "slides": [
            {
                "id": "resumo",
                "tipo": "resumo",
                "titulo": "Resumo geral",
                "itens": [],
            },
            {
                "id": "atrasadas",
                "tipo": "lista",
                "titulo": "Tarefas atrasadas",
                "vazio": "Nenhuma tarefa atrasada 🎉",
                "itens": limitar_itens(atrasadas, hoje, SLIDE_ITEM_LIMIT),
            },
            {
                "id": "hoje",
                "tipo": "lista",
                "titulo": "Entrega hoje",
                "vazio": "Nenhuma tarefa para hoje 🎉",
                "itens": limitar_itens(hoje_lista, hoje, SLIDE_ITEM_LIMIT),
            },
            {
                "id": "amanha",
                "tipo": "lista",
                "titulo": "Entrega amanha",
                "vazio": "Nenhuma tarefa para amanha 🎉",
                "itens": limitar_itens(amanha_lista, hoje, SLIDE_ITEM_LIMIT),
            },
            {
                "id": "proximos-15",
                "tipo": "lista",
                "titulo": "Proximos 15 dias",
                "vazio": "Nenhuma tarefa nos proximos 15 dias 🎉",
                "itens": limitar_itens(proximos_15, hoje, SLIDE_ITEM_LIMIT),
            },
            *slides_setores,
        ],
    }


def create_slides_blueprint(tipos_permitidos):
    slides_bp = Blueprint("slides_bp", __name__)

    @slides_bp.route("/slides")
    @tipos_permitidos("ADMIN", "ATENDENTE", "PCP", "ESPECTADOR")
    def slides():
        return render_template("slides/index.html")

    @slides_bp.route("/api/slides")
    @tipos_permitidos("ADMIN", "ATENDENTE", "PCP", "ESPECTADOR")
    def api_slides():
        return jsonify(montar_payload_slides())

    return slides_bp
