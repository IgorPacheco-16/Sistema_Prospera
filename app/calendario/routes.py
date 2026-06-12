import time
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, render_template, request, session, url_for
from sqlalchemy.orm import load_only, selectinload

from database.models import OP, OPSetor, Setor, Tarefa, User
from tempo import hoje_brasilia


STATUS_PENDENTE = "PENDENTE"
STATUS_EM_ANDAMENTO = "EM ANDAMENTO"
STATUS_EM_VALIDACAO = "EM VALIDA\u00c7\u00c3O"
STATUS_ENTREGUE = "ENTREGUE"
STATUS_EM_ESPERA = "EM ESPERA"

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

PERIODOS_FILTRO = [
    ("todos", "Todos"),
    ("hoje", "Hoje"),
    ("amanha", "Amanh\u00e3"),
    ("7", "Pr\u00f3ximos 7 dias"),
    ("30", "Pr\u00f3ximos 30 dias"),
    ("sem_prazo", "Sem prazo"),
    ("personalizado", "Personalizado"),
]

SECOES_CALENDARIO = [
    ("atrasadas", "Atrasadas"),
    ("hoje", "Hoje"),
    ("amanha", "Amanh\u00e3"),
    ("proximos_7", "Pr\u00f3ximos 7 dias"),
    ("proximos_30", "Pr\u00f3ximos 30 dias"),
    ("sem_prazo", "Sem prazo"),
]


def ids_querystring(nome):
    ids = []
    for valor in request.args.getlist(nome):
        try:
            item_id = int(valor)
        except (TypeError, ValueError):
            continue
        if item_id not in ids:
            ids.append(item_id)
    return ids


def data_querystring(nome):
    valor = request.args.get(nome, "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def bool_querystring(nome):
    return (request.args.get(nome, "") or "").strip().lower() in {
        "1",
        "true",
        "on",
        "sim",
    }


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


def filtros_calendario():
    status = [
        valor
        for valor in request.args.getlist("status")
        if valor in STATUS_FILTRO
    ]
    periodo = request.args.get("periodo", "todos").strip() or "todos"
    periodos_validos = {valor for valor, _rotulo in PERIODOS_FILTRO}
    if periodo not in periodos_validos:
        periodo = "todos"

    tipos_validos = {valor for valor, _rotulo in TIPOS_OP_FILTRO}
    tipos_op = [
        valor
        for valor in request.args.getlist("tipos_op")
        if valor in tipos_validos
    ]

    return {
        "setores": ids_querystring("setores"),
        "ops": ids_querystring("ops"),
        "responsaveis": responsaveis_querystring(),
        "status": status,
        "cliente": request.args.get("cliente", "").strip(),
        "periodo": periodo,
        "data_inicio": data_querystring("data_inicio"),
        "data_fim": data_querystring("data_fim"),
        "tipos_op": tipos_op,
        "apenas_atrasadas": bool_querystring("apenas_atrasadas"),
        "alta_prioridade": bool_querystring("alta_prioridade"),
    }


def ordenar_usuarios_por_nome(usuarios):
    return sorted(
        usuarios,
        key=lambda usuario: (
            (usuario.nome or usuario.email or "").casefold(),
            usuario.id,
        )
    )


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


def op_atrasada(op, hoje):
    return bool(
        op
        and op.prazo_final
        and op.prazo_final < hoje
        and op.status not in ["FINALIZADA", "ARQUIVADA"]
    )


def op_urgente(op, hoje):
    return bool(
        op
        and op.prazo_final
        and hoje <= op.prazo_final <= hoje + timedelta(days=2)
        and op.status not in ["FINALIZADA", "ARQUIVADA"]
    )


def op_no_filtro_tipo(op, tipos_op, alta_prioridade, hoje):
    if alta_prioridade and not getattr(op, "alta_prioridade", False):
        return False
    if "alta_prioridade" in tipos_op and not getattr(op, "alta_prioridade", False):
        return False
    if "op_atrasada" in tipos_op and not op_atrasada(op, hoje):
        return False
    if "op_urgente" in tipos_op and not op_urgente(op, hoje):
        return False
    return True


def intervalo_periodo(filtros):
    inicio = filtros["data_inicio"]
    fim = filtros["data_fim"]
    if inicio and fim and fim < inicio:
        return fim, inicio
    return inicio, fim


def tarefa_no_periodo(tarefa, filtros, hoje):
    prazo = tarefa.prazo
    periodo = filtros["periodo"]

    if filtros["apenas_atrasadas"]:
        return bool(
            prazo
            and prazo < hoje
            and not (getattr(tarefa, "em_espera", False) or tarefa.status == STATUS_EM_ESPERA)
        )
    if periodo == "todos":
        return True
    if periodo == "sem_prazo":
        return prazo is None
    if not prazo:
        return False
    if periodo == "hoje":
        return prazo == hoje
    if periodo == "amanha":
        return prazo == hoje + timedelta(days=1)
    if periodo == "7":
        return hoje <= prazo <= hoje + timedelta(days=7)
    if periodo == "30":
        return hoje <= prazo <= hoje + timedelta(days=30)
    if periodo == "personalizado":
        inicio, fim = intervalo_periodo(filtros)
        if inicio and prazo < inicio:
            return False
        if fim and prazo > fim:
            return False
        return bool(inicio or fim)

    return True


def tarefa_passa_filtros_visuais(tarefa, filtros, hoje):
    if filtros["status"] and status_visual_tarefa(tarefa) not in filtros["status"]:
        return False
    if filtros["cliente"]:
        cliente = (getattr(tarefa.op, "cliente", "") or "").casefold()
        if filtros["cliente"].casefold() not in cliente:
            return False
    if not op_no_filtro_tipo(
        tarefa.op,
        filtros["tipos_op"],
        filtros["alta_prioridade"],
        hoje,
    ):
        return False
    return tarefa_no_periodo(tarefa, filtros, hoje)


def indicador_prazo(tarefa, hoje):
    if getattr(tarefa, "em_espera", False) or tarefa.status == STATUS_EM_ESPERA:
        return {
            "texto": "Em espera",
            "classe": "status-waiting",
            "card_classe": "calendario-card-waiting",
        }

    prazo = tarefa.prazo
    if not prazo:
        return {
            "texto": "Sem prazo",
            "classe": "status-muted",
            "card_classe": "calendario-card-neutral",
        }

    dias = (prazo - hoje).days
    if dias < 0:
        return {
            "texto": f"Atrasada h\u00e1 {abs(dias)} dia(s)",
            "classe": "status-danger",
            "card_classe": "calendario-card-late",
        }
    if dias == 0:
        return {
            "texto": "Vence hoje",
            "classe": "status-warning",
            "card_classe": "calendario-card-today",
        }
    if dias == 1:
        return {
            "texto": "Vence amanh\u00e3",
            "classe": "status-warning",
            "card_classe": "calendario-card-soon",
        }
    if dias <= 7:
        return {
            "texto": f"Em {dias} dias",
            "classe": "status-warning",
            "card_classe": "calendario-card-soon",
        }
    return {
        "texto": f"Em {dias} dias",
        "classe": "status-success",
        "card_classe": "calendario-card-ok",
    }


def chave_secao(tarefa, hoje):
    prazo = tarefa.prazo
    if not prazo:
        return "sem_prazo"
    if prazo < hoje:
        return "atrasadas"
    if prazo == hoje:
        return "hoje"
    if prazo == hoje + timedelta(days=1):
        return "amanha"
    if prazo <= hoje + timedelta(days=7):
        return "proximos_7"
    if prazo <= hoje + timedelta(days=30):
        return "proximos_30"
    return None


def nomes_responsaveis(tarefa):
    responsaveis = ordenar_usuarios_por_nome(list(tarefa.responsaveis or []))
    if not responsaveis:
        return "Geral do setor"
    return ", ".join(
        responsavel.nome or responsavel.email
        for responsavel in responsaveis
    )


def tarefa_card(tarefa, hoje):
    op = tarefa.op
    prazo = indicador_prazo(tarefa, hoje)
    return {
        "tarefa": tarefa,
        "op": op,
        "setor": tarefa.setor,
        "cliente": op.cliente if op else "",
        "responsaveis": nomes_responsaveis(tarefa),
        "status": status_visual_tarefa(tarefa),
        "prazo": prazo,
        "link": url_for(
            "ver_op",
            id=tarefa.op_id,
            setor=tarefa.setor_id,
            tarefa=tarefa.id,
        ),
    }


def chave_ordenacao_card(card):
    tarefa = card["tarefa"]
    op = card["op"]
    prazo = tarefa.prazo
    return (
        0 if getattr(op, "alta_prioridade", False) else 1,
        1 if prazo is None else 0,
        prazo or date.max,
        (op.nome if op else "").casefold(),
        (tarefa.nome or "").casefold(),
        tarefa.id,
    )


def montar_secoes(tarefas, hoje):
    secoes = {
        chave: {
            "chave": chave,
            "titulo": titulo,
            "tarefas": [],
        }
        for chave, titulo in SECOES_CALENDARIO
    }

    for tarefa in tarefas:
        secao = chave_secao(tarefa, hoje)
        if not secao:
            continue
        secoes[secao]["tarefas"].append(tarefa_card(tarefa, hoje))

    for secao in secoes.values():
        secao["tarefas"].sort(key=chave_ordenacao_card)

    return [secoes[chave] for chave, _titulo in SECOES_CALENDARIO]


def resumo_secoes(secoes):
    return {
        secao["chave"]: len(secao["tarefas"])
        for secao in secoes
    }


def filtros_ativos_total(filtros, tipo):
    total = 0
    if tipo != "SETOR":
        total += len(filtros["setores"])
    total += len(filtros["ops"])
    if filtros["responsaveis"]["sem_responsavel"]:
        total += 1
    else:
        total += len(filtros["responsaveis"]["ids"])
    total += len(filtros["status"])
    total += 1 if filtros["cliente"] else 0
    total += 1 if filtros["periodo"] != "todos" else 0
    total += 1 if filtros["data_inicio"] else 0
    total += 1 if filtros["data_fim"] else 0
    total += len(filtros["tipos_op"])
    total += 1 if filtros["apenas_atrasadas"] else 0
    total += 1 if filtros["alta_prioridade"] else 0
    return total


def create_calendario_blueprint(login_required):
    calendario_bp = Blueprint("calendario_bp", __name__)

    @calendario_bp.route("/calendario")
    @login_required
    def calendario():
        inicio_calendario = time.perf_counter()
        hoje = hoje_brasilia()
        tipo = session.get("tipo")
        setor_usuario_id = session.get("setor_id")
        filtros = filtros_calendario()

        query = (
            Tarefa.query
            .options(
                selectinload(Tarefa.op),
                selectinload(Tarefa.setor),
                selectinload(Tarefa.responsaveis).selectinload(User.setor),
            )
            .join(OP, Tarefa.op_id == OP.id)
            .filter(
                Tarefa.validado.is_(False),
                OP.status == "EM ANDAMENTO",
            )
        )

        if tipo == "SETOR":
            query = (
                query
                .join(OPSetor, OPSetor.op_id == OP.id)
                .filter(
                    OPSetor.setor_id == setor_usuario_id,
                    Tarefa.setor_id == setor_usuario_id,
                )
            )
            filtros["setores"] = [setor_usuario_id] if setor_usuario_id else []
        elif filtros["setores"]:
            setores_validos = {
                setor.id
                for setor in Setor.query.filter(Setor.id.in_(filtros["setores"])).all()
            }
            filtros["setores"] = [
                setor_id for setor_id in filtros["setores"] if setor_id in setores_validos
            ]
            if filtros["setores"]:
                query = query.filter(Tarefa.setor_id.in_(filtros["setores"]))

        if filtros["ops"]:
            ops_query = OP.query.filter(
                OP.id.in_(filtros["ops"]),
                OP.status == "EM ANDAMENTO",
            )
            if tipo == "SETOR":
                ops_query = ops_query.join(OPSetor).filter(OPSetor.setor_id == setor_usuario_id)
            ops_validas = {op.id for op in ops_query.all()}
            filtros["ops"] = [op_id for op_id in filtros["ops"] if op_id in ops_validas]
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
        tarefas = [
            tarefa
            for tarefa in tarefas
            if tarefa_passa_filtros_visuais(tarefa, filtros, hoje)
        ]

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
            .options(load_only(OP.id, OP.nome, OP.cliente))
            .join(Tarefa, Tarefa.op_id == OP.id)
            .filter(
                OP.status == "EM ANDAMENTO",
                Tarefa.validado.is_(False),
            )
        )
        if tipo == "SETOR":
            ops_query = (
                ops_query
                .join(OPSetor, OPSetor.op_id == OP.id)
                .filter(
                    OPSetor.setor_id == setor_usuario_id,
                    Tarefa.setor_id == setor_usuario_id,
                )
            )
        ops_disponiveis = ops_query.distinct().order_by(OP.nome).all()

        clientes_query = (
            OP.query
            .with_entities(OP.cliente)
            .join(Tarefa, Tarefa.op_id == OP.id)
            .filter(
                OP.status == "EM ANDAMENTO",
                Tarefa.validado.is_(False),
                OP.cliente.isnot(None),
                OP.cliente != "",
            )
        )
        if tipo == "SETOR":
            clientes_query = (
                clientes_query
                .join(OPSetor, OPSetor.op_id == OP.id)
                .filter(
                    OPSetor.setor_id == setor_usuario_id,
                    Tarefa.setor_id == setor_usuario_id,
                )
            )
        clientes_disponiveis = [
            cliente
            for cliente, in clientes_query.distinct().order_by(OP.cliente).all()
        ]

        secoes = montar_secoes(tarefas, hoje)
        resumo = resumo_secoes(secoes)
        total_tarefas = sum(resumo.values())

        resposta = render_template(
            "calendario/index.html",
            secoes=secoes,
            resumo=resumo,
            total_tarefas=total_tarefas,
            today=hoje,
            tipo=tipo,
            filtros=filtros,
            filtros_ativos_total=filtros_ativos_total(filtros, tipo),
            status_filtro=STATUS_FILTRO,
            setores_disponiveis=setores_disponiveis,
            ops_disponiveis=ops_disponiveis,
            clientes_disponiveis=clientes_disponiveis,
            usuarios_disponiveis=usuarios_disponiveis,
            tipos_op_filtro=TIPOS_OP_FILTRO,
            periodos_filtro=PERIODOS_FILTRO,
        )
        current_app.logger.info(
            "calendario_timing usuario_tipo=%s tarefas=%s total_ms=%.1f",
            tipo,
            total_tarefas,
            (time.perf_counter() - inicio_calendario) * 1000,
        )
        return resposta

    return calendario_bp
