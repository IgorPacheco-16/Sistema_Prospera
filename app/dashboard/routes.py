from datetime import date, datetime

from flask import Blueprint, render_template, request, session

from database.models import OP, Tarefa


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
        filtro_ativo = bool(busca or status or atrasadas_filtro)

        query = OP.query.filter(OP.status != "ARQUIVADA")

        if busca:
            query = query.filter(OP.nome.ilike(f"%{busca}%"))

        ops_base = query.all()

        total = len(ops_base)
        atrasadas = sum(
            1 for op in ops_base
            if op.prazo_final and op.prazo_final < hoje and op.status != "FINALIZADA"
        )
        em_andamento = sum(1 for op in ops_base if op.status == "EM ANDAMENTO")
        finalizadas = sum(1 for op in ops_base if op.status == "FINALIZADA")

        if status:
            ops = [op for op in ops_base if op.status == status]
        else:
            ops = [op for op in ops_base if op.status != "FINALIZADA"]

        lista_ops = []

        for op in ops:
            tarefas = Tarefa.query.filter_by(op_id=op.id).all()

            total_tarefas = len(tarefas)
            validadas = sum(1 for t in tarefas if t.validado)

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

        if atrasadas_filtro:
            lista_ops = [
                item for item in lista_ops
                if item["op"].prazo_final
                and item["op"].prazo_final < hoje
                and item["op"].status != "FINALIZADA"
            ]

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
            tipo=session.get("tipo"),
            ops=lista_ops,
            total=total,
            atrasadas=atrasadas,
            em_andamento=em_andamento,
            finalizadas=finalizadas,
            busca=busca,
            status=status,
            filtro_ativo=filtro_ativo,
            atrasadas_filtro=bool(atrasadas_filtro)
        )

    return dashboard_bp
