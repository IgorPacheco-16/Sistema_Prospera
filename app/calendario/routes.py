from datetime import date, timedelta

from flask import Blueprint, render_template

from database.models import OP, Tarefa, db


def create_calendario_blueprint(login_required):
    calendario_bp = Blueprint("calendario_bp", __name__)

    @calendario_bp.route("/calendario")
    @login_required
    def calendario():
        hoje = date.today()
        amanha = hoje + timedelta(days=1)
        semana = hoje + timedelta(days=7)
        mes = hoje + timedelta(days=30)

        tarefas = Tarefa.query.all()

        hoje_amanha = []
        semana_lista = []
        mes_lista = []

        for t in tarefas:
            if t.prazo and not t.validado:
                op = db.session.get(OP, t.op_id)

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
