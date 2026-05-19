from datetime import date, datetime

from flask import Blueprint, render_template, request, session
from sqlalchemy import case, func

from database.models import db, OP, OPSetor, Tarefa


def create_dashboard_blueprint(login_required, gerar_notificacoes_pendentes):
    dashboard_bp = Blueprint("dashboard_bp", __name__)

    @dashboard_bp.route("/dashboard")
    @login_required
    def dashboard():
        gerar_notificacoes_pendentes()

        hoje = date.today()

        busca = request.args.get("busca", "")
        status = request.args.get("status", "")
        atrasadas_filtro = request.args.get("atrasadas", "")
        filtro = request.args.get("filtro", "")

        def op_atrasada(op):
            return (
                op.prazo_final
                and op.prazo_final < hoje
                and op.status != "FINALIZADA"
            )

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

        if tipo_usuario == "SETOR":
            query = query.join(OPSetor).filter(OPSetor.setor_id == setor_usuario_id)

        if busca:
            query = query.filter(OP.nome.ilike(f"%{busca}%"))

        ops_base = query.all()

        total = sum(
            1 for op in ops_base
            if op.status in ("EM ANDAMENTO", "FINALIZADA") or op_atrasada(op)
        )
        atrasadas = sum(
            1 for op in ops_base
            if op_atrasada(op)
        )
        em_andamento = sum(1 for op in ops_base if op.status == "EM ANDAMENTO")
        finalizadas = sum(1 for op in ops_base if op.status == "FINALIZADA")

        if filtro_dashboard == "total":
            ops = [
                op for op in ops_base
                if op.status in ("EM ANDAMENTO", "FINALIZADA") or op_atrasada(op)
            ]
        elif filtro_dashboard == "atrasadas":
            ops = [op for op in ops_base if op_atrasada(op)]
        elif filtro_dashboard == "finalizadas":
            ops = [op for op in ops_base if op.status == "FINALIZADA"]
        elif filtro_dashboard == "aberta":
            ops = [op for op in ops_base if op.status == "ABERTA"]
        else:
            ops = [op for op in ops_base if op.status == "EM ANDAMENTO"]

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

        lista_ops.sort(
            key=lambda x: (
                not getattr(x["op"], "alta_prioridade", False),
                x["op"].status == "FINALIZADA",
                x["op"].prazo_final is None,
                x["op"].prazo_final or datetime.max.date()
            )
        )

        return render_template(
            "dashboard/index.html",
            usuario=session.get("usuario"),
            tipo=tipo_usuario,
            ops=lista_ops,
            total=total,
            atrasadas=atrasadas,
            em_andamento=em_andamento,
            finalizadas=finalizadas,
            busca=busca,
            status=status,
            filtro_ativo=filtro_ativo,
            atrasadas_filtro=bool(atrasadas_filtro),
            filtro_dashboard=filtro_dashboard
        )

    return dashboard_bp
