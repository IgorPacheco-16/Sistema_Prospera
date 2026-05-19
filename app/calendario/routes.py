from datetime import date, timedelta

from flask import Blueprint, render_template, session

from database.models import OP, Tarefa


def create_calendario_blueprint(login_required):
    calendario_bp = Blueprint("calendario_bp", __name__)

    @calendario_bp.route("/calendario")
    @login_required
    def calendario():
        hoje = date.today()
        amanha = hoje + timedelta(days=1)
        semana = hoje + timedelta(days=7)
        mes = hoje + timedelta(days=30)

        tarefas = Tarefa.query.join(OP, Tarefa.op_id == OP.id).filter(
            Tarefa.prazo.isnot(None),
            Tarefa.validado.is_(False),
            OP.status == "EM ANDAMENTO"
        )

        if session.get("tipo") == "SETOR":
            tarefas = tarefas.filter(Tarefa.setor_id == session.get("setor_id"))

        tarefas = tarefas.all()

        hoje_amanha = []
        semana_lista = []
        mes_lista = []

        for t in tarefas:
            op = t.op

            if t.prazo <= amanha:
                hoje_amanha.append((t, op))
            elif t.prazo <= semana:
                semana_lista.append((t, op))
            elif t.prazo <= mes:
                mes_lista.append((t, op))

        return render_template(
            "calendario/index.html",
            hoje_amanha=hoje_amanha,
            semana=semana_lista,
            mes=mes_lista,
            today=hoje
        )

    return calendario_bp
