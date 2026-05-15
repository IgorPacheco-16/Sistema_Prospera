from flask import Blueprint, render_template

from database.models import OP


def create_ops_blueprint(login_required):
    ops_bp = Blueprint("ops_bp", __name__)

    @ops_bp.route("/arquivadas")
    @login_required
    def arquivadas():
        ops = OP.query.filter_by(status="ARQUIVADA").all()
        return render_template("arquivadas/index.html", ops=ops)

    return ops_bp
