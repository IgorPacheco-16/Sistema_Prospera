import time
from datetime import timedelta

from flask import Blueprint, current_app, render_template, request, session, url_for
from sqlalchemy.orm import load_only, selectinload

from database.models import OP, OPSetor, Setor, Tarefa, User
from tempo import hoje_brasilia


STATUS_PENDENTE = "PENDENTE"
STATUS_EM_ANDAMENTO = "EM ANDAMENTO"
STATUS_EM_VALIDACAO = "EM VALIDA\u00c7\u00c3O"
STATUS_ENTREGUE = "ENTREGUE"
STATUS_EM_ESPERA = "EM ESPERA"


COLUNAS_KANBAN = [
    {
        "chave": "pendentes",
        "titulo": "Pendentes",
        "status": STATUS_PENDENTE,
        "classe": "status-muted",
    },
    {
        "chave": "em_andamento",
        "titulo": "Em andamento",
        "status": STATUS_EM_ANDAMENTO,
        "classe": "status-warning",
    },
    {
        "chave": "em_espera",
        "titulo": "Em espera",
        "status": STATUS_EM_ESPERA,
        "classe": "status-waiting",
    },
    {
        "chave": "em_validacao",
        "titulo": "Em valida\u00e7\u00e3o",
        "status": STATUS_EM_VALIDACAO,
        "classe": "status-warning",
    },
    {
        "chave": "entregues",
        "titulo": "Entregues",
        "status": STATUS_ENTREGUE,
        "classe": "status-success",
    },
]


STATUS_FILTRO = [
    STATUS_PENDENTE,
    STATUS_EM_ANDAMENTO,
    STATUS_EM_ESPERA,
    STATUS_EM_VALIDACAO,
    STATUS_ENTREGUE,
]

TIPOS_OP_FILTRO = [
    ("alta_prioridade", "Alta prioridade"),
    ("op_atrasada", "OP atrasada"),
    ("op_urgente", "OP urgente"),
]

PRAZOS_FILTRO = [
    ("atrasadas", "Atrasadas"),
    ("hoje", "Vencem hoje"),
    ("7", "Pr\u00f3ximos 7 dias"),
    ("30", "Pr\u00f3ximos 30 dias"),
    ("sem_prazo", "Sem prazo"),
]


def ids_querystring(nome):
    ids = []
    for valor in request.args.getlist(nome):
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    return ids


def responsaveis_querystring():
    valores = request.args.getlist("responsavel")

    for valor in request.args.getlist("responsaveis"):
        valores.extend(parte.strip() for parte in valor.split(","))

    if any((valor or "").strip() == "sem_responsavel" for valor in valores):
        return {
            "sem_responsavel": True,
            "ids": [],
        }

    ids = []
    for valor in valores:
        try:
            responsavel_id = int(valor)
        except (TypeError, ValueError):
            continue
        if responsavel_id not in ids:
            ids.append(responsavel_id)

    return {
        "sem_responsavel": False,
        "ids": ids,
    }


def filtros_kanban():
    return {
        "busca": request.args.get("busca", "").strip(),
        "status": request.args.get("status", "todos").strip() or "todos",
        "cliente": request.args.get("cliente", "").strip(),
        "setores": ids_querystring("setores"),
        "ops": ids_querystring("ops"),
        "responsaveis": responsaveis_querystring(),
        "tipos_op": request.args.getlist("tipos_op"),
        "prazos": request.args.getlist("prazos"),
    }


def status_visual_tarefa(tarefa):
    if getattr(tarefa, "em_espera", False) or tarefa.status == STATUS_EM_ESPERA:
        return STATUS_EM_ESPERA
    if tarefa.validado or tarefa.status == STATUS_ENTREGUE:
        return STATUS_ENTREGUE
    if tarefa.entregue or tarefa.status == STATUS_EM_VALIDACAO:
        return STATUS_EM_VALIDACAO
    if tarefa.status == STATUS_EM_ANDAMENTO:
        return STATUS_EM_ANDAMENTO
    return STATUS_PENDENTE


def indicador_prazo(tarefa, hoje):
    if getattr(tarefa, "em_espera", False) or tarefa.status == STATUS_EM_ESPERA:
        return {
            "texto": "Em espera",
            "classe": "status-waiting",
            "card_classe": "kanban-card-waiting",
        }

    if not tarefa.prazo:
        return {
            "texto": "Sem prazo",
            "classe": "status-muted",
            "card_classe": "kanban-card-neutral",
        }

    dias = (tarefa.prazo - hoje).days
    if dias < 0 and not tarefa.validado:
        return {
            "texto": f"Atrasada h\u00e1 {abs(dias)} dia(s)",
            "classe": "status-danger",
            "card_classe": "kanban-card-late",
        }
    if dias == 0 and not tarefa.validado:
        return {
            "texto": "Vence hoje",
            "classe": "status-warning",
            "card_classe": "kanban-card-urgent",
        }
    if dias <= 2 and not tarefa.validado:
        return {
            "texto": f"Urgente: {dias} dia(s)",
            "classe": "status-warning",
            "card_classe": "kanban-card-urgent",
        }

    return {
        "texto": "No prazo",
        "classe": "status-success",
        "card_classe": "kanban-card-ok",
    }


def chave_ordenacao(tarefa, hoje):
    if not tarefa.prazo:
        return (1, 999999)
    return (0, (tarefa.prazo - hoje).days)


def op_atrasada(op, hoje):
    return bool(op.prazo_final and op.prazo_final < hoje)


def op_urgente(op, hoje):
    return bool(
        op.prazo_final
        and hoje <= op.prazo_final <= hoje + timedelta(days=2)
    )


def tarefa_no_filtro_prazo(tarefa, prazos, hoje):
    if not prazos:
        return True
    if getattr(tarefa, "em_espera", False) or tarefa.status == STATUS_EM_ESPERA:
        return "atrasadas" not in prazos

    prazo = tarefa.prazo
    if "sem_prazo" in prazos and not prazo:
        return True
    if not prazo:
        return False
    if "atrasadas" in prazos and prazo < hoje:
        return True
    if "hoje" in prazos and prazo == hoje:
        return True
    if "7" in prazos and hoje <= prazo <= hoje + timedelta(days=7):
        return True
    if "30" in prazos and hoje <= prazo <= hoje + timedelta(days=30):
        return True

    return False


def tarefa_no_filtro_tipo_op(tarefa, tipos_op, hoje):
    if not tipos_op:
        return True

    op = tarefa.op
    if "alta_prioridade" in tipos_op and not op.alta_prioridade:
        return False
    if "op_atrasada" in tipos_op and not op_atrasada(op, hoje):
        return False
    if "op_urgente" in tipos_op and not op_urgente(op, hoje):
        return False

    return True


def tarefa_no_filtro_busca(tarefa, busca):
    if not busca:
        return True

    termo = busca.casefold()
    campos = [
        tarefa.nome,
        tarefa.op.nome if tarefa.op else "",
        tarefa.setor.nome if tarefa.setor else "",
    ]
    return any(termo in (campo or "").casefold() for campo in campos)


def tarefa_no_filtro_cliente(tarefa, cliente):
    if not cliente:
        return True

    cliente_op = (getattr(tarefa.op, "cliente", "") or "").casefold()
    return cliente.casefold() in cliente_op


def aplicar_filtros_visuais(tarefas, filtros, hoje):
    tarefas_filtradas = []

    for tarefa in tarefas:
        status = status_visual_tarefa(tarefa)
        if filtros["status"] != "todos" and filtros["status"] != status:
            continue
        if not tarefa_no_filtro_cliente(tarefa, filtros["cliente"]):
            continue
        if not tarefa_no_filtro_busca(tarefa, filtros["busca"]):
            continue
        if not tarefa_no_filtro_tipo_op(tarefa, filtros["tipos_op"], hoje):
            continue
        if not tarefa_no_filtro_prazo(tarefa, filtros["prazos"], hoje):
            continue

        tarefas_filtradas.append(tarefa)

    return tarefas_filtradas


def ordenar_usuarios_por_nome(usuarios):
    return sorted(
        usuarios,
        key=lambda usuario: (
            (usuario.nome or usuario.email or "").casefold(),
            usuario.id,
        )
    )


def create_kanban_blueprint(login_required):
    kanban_bp = Blueprint("kanban_bp", __name__)

    @kanban_bp.route("/kanban")
    @login_required
    def kanban():
        inicio_kanban = time.perf_counter()
        hoje = hoje_brasilia()
        tipo = session.get("tipo")
        setor_usuario_id = session.get("setor_id")
        filtros = filtros_kanban()

        query = (
            Tarefa.query
            .options(
                selectinload(Tarefa.op),
                selectinload(Tarefa.setor),
                selectinload(Tarefa.responsaveis),
            )
            .join(OP, Tarefa.op_id == OP.id)
            .filter(OP.status.notin_(["FINALIZADA", "ARQUIVADA"]))
        )

        if tipo == "SETOR":
            query = query.filter(Tarefa.setor_id == setor_usuario_id)
            filtros["setores"] = [setor_usuario_id] if setor_usuario_id else []
        elif filtros["setores"]:
            query = query.filter(Tarefa.setor_id.in_(filtros["setores"]))

        if filtros["ops"]:
            query = query.filter(Tarefa.op_id.in_(filtros["ops"]))

        usuarios_disponiveis = []
        if tipo != "ESPECTADOR":
            usuarios_query = (
                User.query
                .options(selectinload(User.setor))
                .filter(User.ativo.is_(True), User.setor_id.isnot(None))
            )
            if tipo == "SETOR":
                usuarios_query = usuarios_query.filter(User.setor_id == setor_usuario_id)
            usuarios_disponiveis = ordenar_usuarios_por_nome(usuarios_query.all())
        usuarios_disponiveis_ids = {usuario.id for usuario in usuarios_disponiveis}

        if tipo == "ESPECTADOR":
            filtros["responsaveis"] = {
                "sem_responsavel": False,
                "ids": [],
            }
        elif filtros["responsaveis"]["sem_responsavel"]:
            query = query.filter(~Tarefa.responsaveis.any())
        elif filtros["responsaveis"]["ids"]:
            responsaveis_permitidos = [
                responsavel_id
                for responsavel_id in filtros["responsaveis"]["ids"]
                if responsavel_id in usuarios_disponiveis_ids
            ]
            filtros["responsaveis"]["ids"] = responsaveis_permitidos
            if responsaveis_permitidos:
                query = query.filter(
                    Tarefa.responsaveis.any(User.id.in_(responsaveis_permitidos))
                ).distinct()

        tarefas = query.all()
        tarefas = aplicar_filtros_visuais(tarefas, filtros, hoje)
        tarefas.sort(key=lambda tarefa: chave_ordenacao(tarefa, hoje))

        setores_disponiveis = (
            Setor.query
            .options(load_only(Setor.id, Setor.nome))
            .order_by(Setor.nome)
            .all()
        )
        if tipo == "SETOR":
            setores_disponiveis = [
                setor
                for setor in setores_disponiveis
                if setor.id == setor_usuario_id
            ]

        ops_query = (
            OP.query
            .options(load_only(OP.id, OP.nome))
            .filter(OP.status.notin_(["FINALIZADA", "ARQUIVADA"]))
        )
        if tipo == "SETOR":
            ops_query = ops_query.join(OPSetor).filter(OPSetor.setor_id == setor_usuario_id)

        ops_disponiveis = ops_query.order_by(OP.nome).all()

        clientes_query = (
            OP.query
            .with_entities(OP.cliente)
            .filter(
                OP.status.notin_(["FINALIZADA", "ARQUIVADA"]),
                OP.cliente.isnot(None),
                OP.cliente != "",
            )
        )
        if tipo == "SETOR":
            clientes_query = clientes_query.join(OPSetor).filter(
                OPSetor.setor_id == setor_usuario_id
            )
        clientes_disponiveis = [
            cliente
            for cliente, in clientes_query.distinct().order_by(OP.cliente).all()
        ]

        colunas = []
        tarefas_por_status = {
            coluna["status"]: []
            for coluna in COLUNAS_KANBAN
        }

        for tarefa in tarefas:
            status = status_visual_tarefa(tarefa)
            prazo = indicador_prazo(tarefa, hoje)
            tarefas_por_status[status].append({
                "tarefa": tarefa,
                "op": tarefa.op,
                "setor": tarefa.setor,
                "status": status,
                "prazo": prazo,
                "link": url_for(
                    "ver_op",
                    id=tarefa.op_id,
                    setor=tarefa.setor_id,
                    tarefa=tarefa.id,
                ),
            })

        for coluna in COLUNAS_KANBAN:
            colunas.append({
                **coluna,
                "tarefas": tarefas_por_status[coluna["status"]],
            })

        resposta = render_template(
            "kanban/index.html",
            colunas=colunas,
            today=hoje,
            tipo=tipo,
            filtros=filtros,
            status_filtro=STATUS_FILTRO,
            setores_disponiveis=setores_disponiveis,
            ops_disponiveis=ops_disponiveis,
            clientes_disponiveis=clientes_disponiveis,
            usuarios_disponiveis=usuarios_disponiveis,
            tipos_op_filtro=TIPOS_OP_FILTRO,
            prazos_filtro=PRAZOS_FILTRO,
        )
        current_app.logger.info(
            "kanban_timing usuario_tipo=%s tarefas=%s total_ms=%.1f",
            tipo,
            len(tarefas),
            (time.perf_counter() - inicio_kanban) * 1000,
        )
        return resposta

    return kanban_bp
