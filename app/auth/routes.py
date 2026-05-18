from datetime import timedelta

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import db, PasswordResetToken, User
from tempo import agora_brasilia


def create_auth_blueprint(
    login_required,
    normalizar_email,
    gerar_codigo_recuperacao,
    enviar_email_recuperacao
):
    auth_bp = Blueprint("auth", __name__)

    @auth_bp.route("/", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = normalizar_email(request.form.get("email"))
            senha = request.form.get("senha")

            user = User.query.filter_by(email=email).first()

            if not user:
                return render_template("auth/login.html", erro="Email ou senha invalidos")

            if not user.ativo:
                return render_template(
                    "auth/login.html",
                    erro="Usuario inativo. Procure um administrador."
                )

            if not user.senha:
                return render_template(
                    "auth/login.html",
                    erro="Usuario sem senha cadastrada. Procure um administrador."
                )

            if check_password_hash(user.senha, senha or ""):
                session["usuario"] = user.email
                session["tipo"] = user.tipo
                session["setor_id"] = user.setor_id
                return redirect(url_for("dashboard"))

            return render_template("auth/login.html", erro="Email ou senha invalidos")

        mensagem = session.pop("mensagem_login", None)
        return render_template("auth/login.html", mensagem=mensagem)

    @auth_bp.route("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @auth_bp.route("/esqueci_senha", methods=["GET", "POST"])
    def esqueci_senha():
        mensagem_generica = (
            "Se o email estiver cadastrado, enviaremos instrucoes para redefinir sua senha."
        )

        if request.method == "POST":
            email = normalizar_email(request.form.get("email"))
            user = User.query.filter_by(email=email).first()
            pode_redefinir = bool(user and user.ativo)
            session["reset_email"] = email

            if pode_redefinir:
                PasswordResetToken.query.filter_by(
                    user_id=user.id,
                    usado=False
                ).update({"usado": True})

                codigo = gerar_codigo_recuperacao()
                token = PasswordResetToken(
                    user_id=user.id,
                    codigo_hash=generate_password_hash(codigo),
                    expira_em=agora_brasilia() + timedelta(minutes=10),
                    usado=False
                )
                db.session.add(token)
                db.session.commit()
                enviar_email_recuperacao(user.email, codigo)
            else:
                db.session.commit()

            return render_template(
                "auth/esqueci_senha.html",
                mensagem=mensagem_generica,
                mostrar_redefinir=True
            )

        return render_template("auth/esqueci_senha.html")

    @auth_bp.route("/redefinir_senha", methods=["GET", "POST"])
    def redefinir_senha():
        email = session.get("reset_email")
        if not email:
            return redirect(url_for("esqueci_senha"))

        user = User.query.filter_by(email=email).first()

        if request.method == "POST":
            codigo = (request.form.get("codigo") or "").strip()
            nova_senha = request.form.get("nova_senha")
            confirmar_senha = request.form.get("confirmar_senha")

            if not codigo or not (nova_senha or "").strip() or not (confirmar_senha or "").strip():
                return render_template(
                    "auth/redefinir_senha.html",
                    erro="Preencha todos os campos."
                )

            if nova_senha != confirmar_senha:
                return render_template(
                    "auth/redefinir_senha.html",
                    erro="A nova senha e a confirmacao nao conferem."
                )

            token = None
            if user and user.ativo:
                token = PasswordResetToken.query.filter_by(
                    user_id=user.id,
                    usado=False
                ).order_by(PasswordResetToken.criado_em.desc()).first()

            if not token:
                return render_template(
                    "auth/redefinir_senha.html",
                    erro="Codigo invalido ou expirado."
                )

            if token.expira_em < agora_brasilia():
                token.usado = True
                db.session.commit()
                return render_template(
                    "auth/redefinir_senha.html",
                    erro="Codigo invalido ou expirado."
                )

            if not check_password_hash(token.codigo_hash, codigo):
                return render_template(
                    "auth/redefinir_senha.html",
                    erro="Codigo invalido ou expirado."
                )

            user.senha = generate_password_hash(nova_senha)
            token.usado = True
            db.session.commit()
            session.pop("reset_email", None)
            session["mensagem_login"] = "Senha redefinida com sucesso. Faca login novamente."

            return redirect(url_for("login"))

        return render_template("auth/redefinir_senha.html")

    @auth_bp.route("/definir_senha", methods=["GET", "POST"])
    def definir_senha():
        if "tmp_user" not in session:
            return redirect(url_for("login"))

        user = db.session.get(User, session["tmp_user"])
        if not user:
            session.pop("tmp_user", None)
            return redirect(url_for("login"))

        if request.method == "POST":
            senha = request.form.get("senha")
            confirmar_senha = request.form.get("confirmar_senha")

            if not (senha or "").strip():
                return render_template(
                    "auth/definir_senha.html",
                    erro="Informe uma senha."
                )

            if confirmar_senha is not None and senha != confirmar_senha:
                return render_template(
                    "auth/definir_senha.html",
                    erro="As senhas nao conferem."
                )

            user.senha = generate_password_hash(senha)
            user.ativo = True

            db.session.commit()

            session.pop("tmp_user")

            return redirect(url_for("login"))

        return render_template("auth/definir_senha.html")

    return auth_bp
