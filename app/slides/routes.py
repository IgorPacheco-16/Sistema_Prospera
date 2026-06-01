import time
from datetime import date, timedelta
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, url_for
from sqlalchemy.orm import selectinload

from database.models import OP, Tarefa
from tempo import hoje_brasilia


SLIDE_ITEM_LIMIT = 5
BASE_DIR = Path(__file__).resolve().parents[2]
SLIDES_ASSET_PATHS = (
    BASE_DIR / "static" / "css" / "slides.css",
    BASE_DIR / "static" / "js" / "slides.js",
)


def slides_asset_version():
    mtimes = [
        int(caminho.stat().st_mtime)
        for caminho in SLIDES_ASSET_PATHS
        if caminho.exists()
    ]
    return str(max(mtimes) if mtimes else 1)


def status_visual_tarefa(tarefa):
    if tarefa.validado:
        return "ENTREGUE"
    if tarefa.entregue:
        return "EM VALIDAÇÃO"
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
        "amanha": "Entrega amanhã",
        "proximos_15_dias": "Próximos 15 dias",
        "futura": "Futura",
        "sem_prazo": "Sem prazo",
    }
    return textos.get(urgencia, "Sem classificação")


def data_iso(valor):
    return valor.isoformat() if valor else None


def data_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else "Sem prazo"


def cliente_op(op):
    cliente = (getattr(op, "cliente", None) or "").strip() if op else ""
    return cliente or "Não informado"


def nomes_responsaveis(tarefa):
    responsaveis = sorted(
        list(getattr(tarefa, "responsaveis", []) or []),
        key=lambda usuario: ((usuario.nome or usuario.email or "").casefold(), usuario.id),
    )
    if not responsaveis:
        return "Geral do setor"
    return ", ".join(
        responsavel.nome or responsavel.email
        for responsavel in responsaveis
    )


def item_tarefa(tarefa, hoje):
    urgencia = urgencia_tarefa(tarefa, hoje)
    op = tarefa.op
    setor = tarefa.setor
    op_id = tarefa.op_id if tarefa.op_id else None

    return {
        "id": tarefa.id,
        "op_id": op_id,
        "op": op.nome if op else "OP não informada",
        "cliente": cliente_op(op),
        "tarefa": tarefa.nome or "Tarefa sem nome",
        "setor": setor.nome if setor else "Sem setor",
        "responsavel": nomes_responsaveis(tarefa),
        "responsaveis": nomes_responsaveis(tarefa),
        "prazo": data_iso(tarefa.prazo),
        "prazo_formatado": data_br(tarefa.prazo),
        "status": status_visual_tarefa(tarefa),
        "urgencia": urgencia,
        "urgencia_texto": texto_urgencia(urgencia),
        "alta_prioridade": bool(getattr(op, "alta_prioridade", False)),
        "link": url_for("ver_op", id=op_id) if op_id else "",
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
            selectinload(Tarefa.responsaveis),
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


def paginar_slides_tarefas(
    tarefas,
    hoje,
    id_base,
    titulo,
    vazio=None,
    incluir_vazio=False,
):
    tarefas_ordenadas = sorted(tarefas, key=ordenar_tarefas)

    if not tarefas_ordenadas:
        if not incluir_vazio:
            return []
        return [
            {
                "id": id_base,
                "tipo": "lista",
                "titulo": titulo,
                "vazio": vazio or "Nenhuma tarefa",
                "itens": [],
            }
        ]

    total_paginas = (len(tarefas_ordenadas) + SLIDE_ITEM_LIMIT - 1) // SLIDE_ITEM_LIMIT
    slides = []
    for indice in range(total_paginas):
        inicio = indice * SLIDE_ITEM_LIMIT
        pagina = tarefas_ordenadas[inicio:inicio + SLIDE_ITEM_LIMIT]
        numero_pagina = indice + 1

        slides.append(
            {
                "id": f"{id_base}-{numero_pagina}" if total_paginas > 1 else id_base,
                "tipo": "lista",
                "titulo": (
                    f"{titulo} {numero_pagina}/{total_paginas}"
                    if total_paginas > 1
                    else titulo
                ),
                "vazio": vazio or "Nenhuma tarefa",
                "itens": [item_tarefa(tarefa, hoje) for tarefa in pagina],
            }
        )

    return slides


def montar_payload_slides():
    hoje = hoje_brasilia()
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

    slides_setores = []
    for nome_setor, tarefas_setor in sorted(setores.items()):
        slides_setores.extend(
            paginar_slides_tarefas(
                tarefas_setor,
                hoje,
                f"setor-{nome_setor.lower().replace(' ', '-')}",
                nome_setor,
                f"Nenhuma tarefa em {nome_setor}",
            )
        )

    slides = [
        {
            "id": "resumo",
            "tipo": "resumo",
            "titulo": "Resumo geral",
            "itens": [],
        },
        *paginar_slides_tarefas(
            atrasadas,
            hoje,
            "atrasadas",
            "Tarefas atrasadas",
            "Não há tarefas em atraso, parabéns!",
            incluir_vazio=True,
        ),
        *paginar_slides_tarefas(
            hoje_lista,
            hoje,
            "hoje",
            "Entrega hoje",
            "Nenhuma tarefa para hoje",
        ),
        *paginar_slides_tarefas(
            amanha_lista,
            hoje,
            "amanha",
            "Entrega amanhã",
            "Nenhuma tarefa para amanhã",
        ),
        *paginar_slides_tarefas(
            proximos_15,
            hoje,
            "proximos-15",
            "Próximos 15 dias",
            "Nenhuma tarefa nos próximos 15 dias",
        ),
        *slides_setores,
    ]

    return {
        "atualizado_em": hoje.isoformat(),
        "intervalos": {
            "atualizacao_ms": 90000,
            "slide_ms": 8000,
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
        "slides": slides,
    }


def create_slides_blueprint(tipos_permitidos):
    slides_bp = Blueprint("slides_bp", __name__)

    @slides_bp.route("/slides")
    @tipos_permitidos("ADMIN", "ATENDENTE", "PCP", "ESPECTADOR")
    def slides():
        return render_template(
            "slides/index.html",
            slides_asset_version=slides_asset_version()
        )

    @slides_bp.route("/api/slides")
    @tipos_permitidos("ADMIN", "ATENDENTE", "PCP", "ESPECTADOR")
    def api_slides():
        inicio_slides = time.perf_counter()
        payload = montar_payload_slides()
        resposta = jsonify(payload)
        current_app.logger.info(
            "api_slides_timing slides=%s total_ms=%.1f",
            len(payload.get("slides", [])),
            (time.perf_counter() - inicio_slides) * 1000,
        )
        return resposta

    return slides_bp
