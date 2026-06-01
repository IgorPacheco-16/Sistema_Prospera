import os
import time

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from database.models import db, Notificacao
from tempo import formatar_data_hora_brasilia


def create_notificacoes_blueprint(
    login_required,
    is_setor,
    gerar_notificacoes_pendentes,
    query_notificacoes_usuario,
    notificacao_pertence_ao_usuario_logado,
    criar_notificacao,
    categoria_notificacao
):
    notificacoes_bp = Blueprint("notificacoes", __name__)

    @notificacoes_bp.route("/notificacoes")
    @login_required
    def notificacoes():
        inicio_notificacoes = time.perf_counter()
        gerar_notificacoes_pendentes(enviar_emails=False)

        lista = query_notificacoes_usuario().order_by(
            Notificacao.data.desc()
        ).limit(30).all()

        resposta = render_template("notificacoes/index.html", notificacoes=lista)
        current_app.logger.info(
            "notificacoes_timing usuario_tipo=%s notificacoes=%s total_ms=%.1f",
            session.get("tipo"),
            len(lista),
            (time.perf_counter() - inicio_notificacoes) * 1000,
        )
        return resposta

    @notificacoes_bp.route("/ler_notificacao/<int:id>", methods=["POST"])
    @login_required
    def ler_notificacao(id):
        notif = Notificacao.query.get_or_404(id)

        if not notificacao_pertence_ao_usuario_logado(notif):
            return "Acesso negado", 403

        notif.lida = True
        db.session.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            total = query_notificacoes_usuario().filter_by(lida=False).count()
            return jsonify({
                "ok": True,
                "total": total,
                "id": notif.id
            })

        return redirect(request.referrer or url_for("dashboard"))

    @notificacoes_bp.route("/notificacoes/marcar_todas_lidas", methods=["POST"])
    @login_required
    def marcar_todas_notificacoes_lidas():
        query_notificacoes_usuario().filter_by(lida=False).update(
            {"lida": True},
            synchronize_session=False
        )
        db.session.commit()

        mensagem = "Todas as notificações foram marcadas como lidas."

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "ok": True,
                "total": 0,
                "mensagem": mensagem
            })

        flash(mensagem, "success")
        return redirect(request.referrer or url_for("notificacoes"))

    @notificacoes_bp.route("/api/notificacoes")
    @login_required
    def api_notificacoes():
        gerar_notificacoes_pendentes(enviar_emails=False)

        total = query_notificacoes_usuario().filter_by(lida=False).count()

        recentes = query_notificacoes_usuario().order_by(
            Notificacao.data.desc()
        ).limit(8).all()

        return jsonify({
            "total": total,
            "notificacoes": [
                {
                    "id": n.id,
                    "mensagem": n.mensagem,
                    "link": n.link,
                    "op_id": n.op_id,
                    "tarefa_id": n.tarefa_id,
                    "setor_id": n.setor_id,
                    "tipo_evento": n.tipo_evento,
                    "categoria": categoria_notificacao(n.tipo_evento),
                    "lida": n.lida,
                    "data": formatar_data_hora_brasilia(n.data)
                }
                for n in recentes
            ]
        })

    @notificacoes_bp.route("/teste_notificacao")
    @login_required
    def teste_notificacao():
        app_env = os.environ.get("APP_ENV", "production").strip().lower() or "production"
        if app_env not in {"development", "test"}:
            abort(404)

        if session.get("tipo") != "ADMIN":
            return "Acesso negado", 403

        criar_notificacao(
            session.get("tipo"),
            "Teste de notificação no dashboard",
            link=url_for("dashboard"),
            tipo_evento="teste_notificacao"
        )
        db.session.commit()

        return "OK"

    return notificacoes_bp
