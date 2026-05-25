from datetime import timedelta

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import CadastroPendente, db, PasswordResetToken, Setor, User
from tempo import agora_brasilia


MAX_TENTATIVAS_CADASTRO = 5


def create_auth_blueprint(
    login_required,
    normalizar_email,
    gerar_codigo_recuperacao,
    enviar_email_recuperacao,
    enviar_email_cadastro,
    criar_notificacao=None
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
                session.clear()
                return render_template(
                    "auth/login.html",
                    erro="Sua conta foi criada e está aguardando aprovação de um administrador."
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

    def cadastro_pendente_da_sessao():
        email = session.get("cadastro_email")
        if not email:
            return None

        return CadastroPendente.query.filter_by(email=email).first()

    def cadastro_valido_para_finalizar():
        cadastro = cadastro_pendente_da_sessao()
        if not cadastro or not cadastro.verificado:
            return None

        if cadastro.expira_em < agora_brasilia():
            db.session.delete(cadastro)
            db.session.commit()
            session.pop("cadastro_email", None)
            session.pop("cadastro_verificado", None)
            return None

        return cadastro

    @auth_bp.route("/criar_conta", methods=["GET", "POST"])
    def criar_conta():
        if request.method == "POST":
            email = normalizar_email(request.form.get("email"))

            if not email:
                return render_template(
                    "auth/criar_conta_email.html",
                    erro="Informe o e-mail."
                )

            if User.query.filter_by(email=email).first():
                return render_template(
                    "auth/criar_conta_email.html",
                    erro="Este e-mail já está cadastrado."
                )

            codigo = gerar_codigo_recuperacao()
            cadastro = CadastroPendente.query.filter_by(email=email).first()
            if not cadastro:
                cadastro = CadastroPendente(email=email)
                db.session.add(cadastro)

            cadastro.codigo_hash = generate_password_hash(codigo)
            cadastro.expira_em = agora_brasilia() + timedelta(minutes=15)
            cadastro.tentativas = 0
            cadastro.verificado = False
            cadastro.criado_em = agora_brasilia()

            if not enviar_email_cadastro(email, codigo):
                db.session.rollback()
                return render_template(
                    "auth/criar_conta_email.html",
                    erro=(
                        "Não foi possível enviar o código agora. "
                        "Tente novamente mais tarde."
                    )
                )

            db.session.commit()
            session["cadastro_email"] = email
            session.pop("cadastro_verificado", None)
            return redirect(url_for("auth.validar_codigo_cadastro"))

        return render_template("auth/criar_conta_email.html")

    @auth_bp.route("/criar_conta/codigo", methods=["GET", "POST"])
    def validar_codigo_cadastro():
        cadastro = cadastro_pendente_da_sessao()
        if not cadastro:
            return redirect(url_for("auth.criar_conta"))

        if request.method == "POST":
            codigo = (request.form.get("codigo") or "").strip()

            if cadastro.expira_em < agora_brasilia():
                db.session.delete(cadastro)
                db.session.commit()
                session.pop("cadastro_email", None)
                session.pop("cadastro_verificado", None)
                return render_template(
                    "auth/criar_conta_codigo.html",
                    erro="Código inválido ou expirado."
                )

            if cadastro.tentativas >= MAX_TENTATIVAS_CADASTRO:
                return render_template(
                    "auth/criar_conta_codigo.html",
                    erro="Muitas tentativas incorretas. Solicite um novo código."
                )

            if not codigo or not check_password_hash(cadastro.codigo_hash, codigo):
                cadastro.tentativas += 1
                db.session.commit()
                if cadastro.tentativas >= MAX_TENTATIVAS_CADASTRO:
                    erro = "Muitas tentativas incorretas. Solicite um novo código."
                else:
                    erro = "Código inválido ou expirado."
                return render_template("auth/criar_conta_codigo.html", erro=erro)

            cadastro.verificado = True
            cadastro.tentativas = 0
            db.session.commit()
            session["cadastro_verificado"] = True
            return redirect(url_for("auth.finalizar_cadastro"))

        return render_template("auth/criar_conta_codigo.html")

    @auth_bp.route("/criar_conta/finalizar", methods=["GET", "POST"])
    def finalizar_cadastro():
        cadastro = cadastro_valido_para_finalizar()
        if not cadastro:
            return redirect(url_for("auth.criar_conta"))

        setores = Setor.query.order_by(Setor.nome).all()

        if request.method == "POST":
            nome = (request.form.get("nome") or "").strip()
            senha = request.form.get("senha")
            confirmar_senha = request.form.get("confirmar_senha")
            setor_id = request.form.get("setor")

            if User.query.filter_by(email=cadastro.email).first():
                db.session.delete(cadastro)
                db.session.commit()
                session.pop("cadastro_email", None)
                session.pop("cadastro_verificado", None)
                return render_template(
                    "auth/criar_conta_email.html",
                    erro="Este e-mail já está cadastrado."
                )

            if not nome:
                return render_template(
                    "auth/criar_conta_finalizar.html",
                    setores=setores,
                    erro="Informe o nome."
                )

            if not (senha or "").strip() or not (confirmar_senha or "").strip():
                return render_template(
                    "auth/criar_conta_finalizar.html",
                    setores=setores,
                    erro="Informe a senha e a confirmação."
                )

            if senha != confirmar_senha:
                return render_template(
                    "auth/criar_conta_finalizar.html",
                    setores=setores,
                    erro="A senha e a confirmação não conferem."
                )

            try:
                setor_id_convertido = int(setor_id) if setor_id else None
            except ValueError:
                setor_id_convertido = None

            setor = db.session.get(Setor, setor_id_convertido) if setor_id_convertido else None
            if not setor:
                return render_template(
                    "auth/criar_conta_finalizar.html",
                    setores=setores,
                    erro="Informe um setor válido."
                )

            db.session.add(User(
                nome=nome,
                email=cadastro.email,
                senha=generate_password_hash(senha),
                tipo="SETOR",
                setor_id=setor.id,
                ativo=False
            ))

            if criar_notificacao:
                criar_notificacao(
                    usuario="ADMIN",
                    mensagem=f"Novo cadastro aguardando aprovação: {cadastro.email}",
                    link=url_for("listar_usuarios")
                )

            db.session.delete(cadastro)
            db.session.commit()
            session.pop("cadastro_email", None)
            session.pop("cadastro_verificado", None)
            session["mensagem_login"] = (
                "Conta criada com sucesso. Aguarde aprovação de um administrador."
            )
            return redirect(url_for("login"))

        return render_template("auth/criar_conta_finalizar.html", setores=setores)

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
