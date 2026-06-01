import time

from flask import Blueprint, current_app, render_template, request, session
from sqlalchemy import and_, case, func, not_, or_

from database.models import db, OP, OPSetor, Tarefa, TarefaResponsavel, User
from metricas_responsaveis import (
    STATUS_EM_ANDAMENTO,
    STATUS_EM_VALIDACAO,
    STATUS_ENTREGUE,
    finalizar_resumo,
    nova_linha_usuario,
)
from tempo import hoje_brasilia


OPS_POR_PAGINA_DASHBOARD = 18


def paginas_numericas(pagina_atual, total_paginas, raio=1):
    if total_paginas <= 7:
        return list(range(1, total_paginas + 1))

    paginas = {1, total_paginas}
    for pagina in range(pagina_atual - raio, pagina_atual + raio + 1):
        if 1 <= pagina <= total_paginas:
            paginas.add(pagina)

    resultado = []
    pagina_anterior = None
    for pagina in sorted(paginas):
        if pagina_anterior is not None and pagina - pagina_anterior > 1:
            resultado.append(None)
        resultado.append(pagina)
        pagina_anterior = pagina

    return resultado


def contar_ops(query):
    return int(query.with_entities(func.count(OP.id)).order_by(None).scalar() or 0)


def condicao_op_atrasada(hoje):
    return and_(
        OP.prazo_final < hoje,
        OP.status != "FINALIZADA",
    )


def metricas_usuario_dashboard(usuario, hoje):
    resumo = nova_linha_usuario(usuario)
    usuario_id = getattr(usuario, "id", None)
    if not usuario_id:
        return finalizar_resumo(resumo)

    tarefa_concluida = or_(
        Tarefa.concluida_em.isnot(None),
        Tarefa.validada_em.isnot(None),
        Tarefa.validado.is_(True),
    )
    sinal_entregue = or_(
        Tarefa.entregue.is_(True),
        Tarefa.status.in_([STATUS_EM_VALIDACAO, STATUS_ENTREGUE]),
        Tarefa.enviada_validacao_em.isnot(None),
    )
    sinal_em_andamento = or_(
        Tarefa.status == STATUS_EM_ANDAMENTO,
        Tarefa.iniciada_em.isnot(None),
    )

    def contar_tarefas_distintas(condicao):
        return func.count(func.distinct(case((condicao, Tarefa.id), else_=None)))

    linha = (
        db.session.query(
            func.count(func.distinct(Tarefa.id)).label("total_atribuidas"),
            contar_tarefas_distintas(tarefa_concluida).label("concluidas"),
            contar_tarefas_distintas(and_(not_(tarefa_concluida), sinal_entregue)).label("entregues"),
            contar_tarefas_distintas(and_(
                not_(tarefa_concluida),
                not_(sinal_entregue),
                sinal_em_andamento,
            )).label("em_andamento"),
            contar_tarefas_distintas(not_(tarefa_concluida)).label("abertas"),
            contar_tarefas_distintas(and_(
                Tarefa.prazo < hoje,
                not_(tarefa_concluida),
            )).label("atrasadas"),
            contar_tarefas_distintas(or_(
                Tarefa.recusada_em.isnot(None),
                Tarefa.motivo_recusa.isnot(None),
            )).label("recusadas"),
        )
        .join(TarefaResponsavel, TarefaResponsavel.tarefa_id == Tarefa.id)
        .join(OP, OP.id == Tarefa.op_id)
        .filter(
            TarefaResponsavel.usuario_id == usuario_id,
            TarefaResponsavel.status == "ACEITO",
            TarefaResponsavel.ativo.is_(True),
            OP.status != "ARQUIVADA",
            OP.arquivada_em.is_(None),
        )
        .one()
    )

    for chave in [
        "total_atribuidas",
        "concluidas",
        "entregues",
        "em_andamento",
        "abertas",
        "atrasadas",
        "recusadas",
    ]:
        resumo[chave] = int(getattr(linha, chave) or 0)

    resumo["pendentes"] = max(
        resumo["total_atribuidas"]
        - resumo["concluidas"]
        - resumo["entregues"]
        - resumo["em_andamento"],
        0,
    )

    return finalizar_resumo(resumo)


def create_dashboard_blueprint(login_required, gerar_notificacoes_pendentes):
    dashboard_bp = Blueprint("dashboard_bp", __name__)

    @dashboard_bp.route("/dashboard")
    @login_required
    def dashboard():
        inicio_dashboard = time.perf_counter()
        tempos = {}

        def marcar_tempo(etapa):
            tempos[etapa] = round((time.perf_counter() - inicio_dashboard) * 1000, 1)

        try:
            gerar_notificacoes_pendentes(enviar_emails=False)
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "dashboard_notificacoes_nao_geradas"
            )
        finally:
            marcar_tempo("notificacoes_ms")

        hoje = hoje_brasilia()

        busca = request.args.get("busca", "")
        status = request.args.get("status", "")
        atrasadas_filtro = request.args.get("atrasadas", "")
        filtro = request.args.get("filtro", "")
        pagina_atual = request.args.get("page", 1, type=int) or 1
        if pagina_atual < 1:
            pagina_atual = 1

        if status == "FINALIZADA":
            filtro_dashboard = "finalizadas"
        elif status == "EM ANDAMENTO":
            filtro_dashboard = "em_andamento"
        elif status == "ABERTA":
            filtro_dashboard = "aberta"
        elif atrasadas_filtro:
            filtro_dashboard = "atrasadas"
        elif filtro == "total":
            filtro_dashboard = "total"
        else:
            filtro_dashboard = "em_andamento"

        filtro_ativo = bool(busca or status or atrasadas_filtro or filtro)

        query = OP.query.filter(OP.status != "ARQUIVADA")
        tipo_usuario = session.get("tipo")
        setor_usuario_id = session.get("setor_id")
        usuario_logado = User.query.filter_by(email=session.get("usuario")).first()

        if tipo_usuario == "SETOR":
            ops_setor = db.session.query(OPSetor.op_id).filter(
                OPSetor.setor_id == setor_usuario_id
            )
            query = query.filter(OP.id.in_(ops_setor))

        if busca:
            query = query.filter(OP.nome.ilike(f"%{busca}%"))

        atrasada = condicao_op_atrasada(hoje)
        total = contar_ops(query.filter(or_(
            OP.status.in_(["EM ANDAMENTO", "FINALIZADA"]),
            atrasada,
        )))
        atrasadas = contar_ops(query.filter(atrasada))
        em_andamento = contar_ops(query.filter(OP.status == "EM ANDAMENTO"))
        finalizadas = contar_ops(query.filter(OP.status == "FINALIZADA"))
        marcar_tempo("contadores_ms")

        if filtro_dashboard == "total":
            query_ops = query.filter(or_(
                OP.status.in_(["EM ANDAMENTO", "FINALIZADA"]),
                atrasada,
            ))
        elif filtro_dashboard == "atrasadas":
            query_ops = query.filter(atrasada)
        elif filtro_dashboard == "finalizadas":
            query_ops = query.filter(OP.status == "FINALIZADA")
        elif filtro_dashboard == "aberta":
            query_ops = query.filter(OP.status == "ABERTA")
        else:
            query_ops = query.filter(OP.status == "EM ANDAMENTO")

        total_filtrado = contar_ops(query_ops)
        marcar_tempo("ops_total_filtrado_ms")
        total_paginas = max(
            (total_filtrado + OPS_POR_PAGINA_DASHBOARD - 1) // OPS_POR_PAGINA_DASHBOARD,
            1,
        )
        if pagina_atual > total_paginas:
            pagina_atual = total_paginas

        offset = (pagina_atual - 1) * OPS_POR_PAGINA_DASHBOARD
        query_ops_ordenada = query_ops.order_by(
            case((OP.alta_prioridade.is_(True), 0), else_=1),
            case((OP.status == "FINALIZADA", 1), else_=0),
            case((OP.prazo_final.is_(None), 1), else_=0),
            OP.prazo_final,
            OP.id,
        )
        ops = query_ops_ordenada.limit(OPS_POR_PAGINA_DASHBOARD).offset(offset).all()
        marcar_tempo("ops_paginadas_ms")

        op_ids = [op.id for op in ops]
        tarefas_por_op = {}
        if op_ids:
            tarefas_query = db.session.query(
                Tarefa.op_id,
                func.count(Tarefa.id).label("total_tarefas"),
                func.coalesce(
                    func.sum(case((Tarefa.validado == True, 1), else_=0)),
                    0
                ).label("validadas"),
            ).filter(Tarefa.op_id.in_(op_ids))

            if tipo_usuario == "SETOR":
                tarefas_query = tarefas_query.filter(Tarefa.setor_id == setor_usuario_id)

            tarefas_por_op = {
                linha.op_id: {
                    "total_tarefas": int(linha.total_tarefas or 0),
                    "validadas": int(linha.validadas or 0),
                }
                for linha in tarefas_query.group_by(Tarefa.op_id).all()
            }
        marcar_tempo("tarefas_por_op_ms")

        lista_ops = []
        for op in ops:
            resumo_tarefas = tarefas_por_op.get(op.id, {})
            total_tarefas = resumo_tarefas.get("total_tarefas", 0)
            validadas = resumo_tarefas.get("validadas", 0)

            if op.status == "FINALIZADA":
                cor = "finalizada"
            elif op.prazo_final and op.prazo_final < hoje:
                cor = "vermelho"
            elif op.prazo_final and (op.prazo_final - hoje).days <= 2:
                cor = "laranja"
            elif op.prazo_final and (op.prazo_final - hoje).days <= 5:
                cor = "amarelo"
            else:
                cor = "verde"

            lista_ops.append({
                "op": op,
                "cor": cor,
                "total_tarefas": total_tarefas,
                "validadas": validadas
            })

        inicio_exibicao = offset + 1 if total_filtrado else 0
        fim_exibicao = offset + len(lista_ops) if total_filtrado else 0
        argumentos_paginacao = {}
        for chave, valores in request.args.lists():
            if chave == "page":
                continue
            valores_validos = [valor for valor in valores if valor]
            if len(valores_validos) == 1:
                argumentos_paginacao[chave] = valores_validos[0]
            elif valores_validos:
                argumentos_paginacao[chave] = valores_validos

        paginacao = {
            "pagina_atual": pagina_atual,
            "total_paginas": total_paginas,
            "por_pagina": OPS_POR_PAGINA_DASHBOARD,
            "total_itens": total_filtrado,
            "inicio": inicio_exibicao,
            "fim": fim_exibicao,
            "tem_anterior": pagina_atual > 1,
            "tem_proxima": pagina_atual < total_paginas,
            "pagina_anterior": pagina_atual - 1,
            "pagina_proxima": pagina_atual + 1,
            "paginas": paginas_numericas(pagina_atual, total_paginas),
            "argumentos": argumentos_paginacao,
        }

        minhas_metricas = metricas_usuario_dashboard(usuario_logado, hoje)
        marcar_tempo("minhas_metricas_ms")

        resposta = render_template(
            "dashboard/index.html",
            usuario=session.get("usuario"),
            tipo=tipo_usuario,
            minhas_metricas=minhas_metricas,
            ops=lista_ops,
            total=total,
            atrasadas=atrasadas,
            em_andamento=em_andamento,
            finalizadas=finalizadas,
            busca=busca,
            status=status,
            filtro_ativo=filtro_ativo,
            atrasadas_filtro=bool(atrasadas_filtro),
            filtro_dashboard=filtro_dashboard,
            paginacao=paginacao,
        )
        marcar_tempo("render_ms")

        current_app.logger.info(
            "dashboard_timing usuario_tipo=%s ops=%s total_filtrado=%s pagina=%s/%s total_ms=%.1f etapas=%s",
            tipo_usuario,
            len(lista_ops),
            total_filtrado,
            pagina_atual,
            total_paginas,
            (time.perf_counter() - inicio_dashboard) * 1000,
            tempos,
        )
        return resposta

    return dashboard_bp
