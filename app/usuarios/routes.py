from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import db, Setor, User


def create_usuarios_blueprint(login_required, tipos_permitidos, normalizar_email):
    usuarios_bp = Blueprint("usuarios", __name__)
    tipos = ["ADMIN", "ATENDENTE", "PCP", "SETOR", "ESPECTADOR"]

    def contexto_formulario(**extra):
        contexto = {
            "setores": Setor.query.order_by(Setor.nome).all(),
            "tipos": tipos,
        }
        contexto.update(extra)
        return contexto

    def validar_dados_usuario(email, tipo, setor_id):
        if not email:
            return None, "Informe o email."

        if tipo not in tipos:
            return None, "Tipo de usuario invalido."

        if tipo == "SETOR" and not setor_id:
            return None, "Informe o setor para usuarios do tipo SETOR."

        try:
            setor_id_convertido = int(setor_id) if setor_id else None
        except ValueError:
            setor_id_convertido = None

        if tipo == "SETOR" and not setor_id_convertido:
            return None, "Setor invalido."

        if setor_id_convertido and not db.session.get(Setor, setor_id_convertido):
            return None, "Setor invalido."

        return setor_id_convertido, None

    def usuario_logado_email():
        return normalizar_email(session.get("usuario"))

    @usuarios_bp.route("/criar_usuario", methods=["GET", "POST"])
    @tipos_permitidos("ADMIN")
    def criar_usuario():
        if request.method == "POST":
            email = normalizar_email(request.form.get("email"))
            tipo = request.form.get("tipo")
            setor_id = request.form.get("setor")
            senha = request.form.get("senha")

            setor_id_convertido, erro = validar_dados_usuario(email, tipo, setor_id)
            if erro:
                return render_template(
                    "usuario/criar_usuario.html",
                    **contexto_formulario(erro=erro)
                )

            if User.query.filter_by(email=email).first():
                return render_template(
                    "usuario/criar_usuario.html",
                    **contexto_formulario(erro="Ja existe um usuario com este email.")
                )

            if not (senha or "").strip():
                return render_template(
                    "usuario/criar_usuario.html",
                    **contexto_formulario(erro="Informe a senha inicial.")
                )

            novo_usuario = User(
                email=email,
                tipo=tipo,
                setor_id=setor_id_convertido,
                senha=generate_password_hash(senha),
                ativo=True
            )

            db.session.add(novo_usuario)
            db.session.commit()

            return render_template(
                "usuario/criar_usuario.html",
                **contexto_formulario(mensagem="Usuario criado com sucesso.")
            )

        return render_template("usuario/criar_usuario.html", **contexto_formulario())

    @usuarios_bp.route("/usuarios")
    @tipos_permitidos("ADMIN")
    def listar_usuarios():
        usuarios = User.query.order_by(User.email).all()
        return render_template("usuario/listar_usuarios.html", usuarios=usuarios)

    @usuarios_bp.route("/usuarios/<int:id>/editar", methods=["GET", "POST"])
    @tipos_permitidos("ADMIN")
    def editar_usuario(id):
        usuario = User.query.get_or_404(id)

        if request.method == "POST":
            usuario_atual_logado = usuario.email == usuario_logado_email()
            email = normalizar_email(request.form.get("email"))
            tipo = request.form.get("tipo")
            setor_id = request.form.get("setor")
            ativo = request.form.get("ativo") == "on"
            nova_senha = request.form.get("nova_senha")

            setor_id_convertido, erro = validar_dados_usuario(email, tipo, setor_id)
            if erro:
                return render_template(
                    "usuario/editar_usuario.html",
                    **contexto_formulario(usuario=usuario, erro=erro)
                )

            email_existente = User.query.filter(
                User.email == email,
                User.id != usuario.id
            ).first()
            if email_existente:
                return render_template(
                    "usuario/editar_usuario.html",
                    **contexto_formulario(
                        usuario=usuario,
                        erro="Ja existe outro usuario com este email."
                    )
                )

            usuario.email = email
            usuario.tipo = tipo
            usuario.setor_id = setor_id_convertido
            usuario.ativo = True if usuario_atual_logado else ativo

            if (nova_senha or "").strip():
                usuario.senha = generate_password_hash(nova_senha)

            if usuario_atual_logado:
                session["usuario"] = usuario.email
                session["tipo"] = usuario.tipo
                session["setor_id"] = usuario.setor_id

            db.session.commit()
            return redirect(url_for("listar_usuarios"))

        return render_template(
            "usuario/editar_usuario.html",
            **contexto_formulario(usuario=usuario)
        )

    @usuarios_bp.route("/usuarios/<int:id>/alternar_status", methods=["POST"])
    @tipos_permitidos("ADMIN")
    def alternar_status_usuario(id):
        usuario = User.query.get_or_404(id)

        if usuario.email == usuario_logado_email():
            return redirect(url_for("listar_usuarios"))

        usuario.ativo = not usuario.ativo
        db.session.commit()
        return redirect(url_for("listar_usuarios"))

    @usuarios_bp.route("/usuarios/<int:id>/excluir", methods=["POST"])
    @tipos_permitidos("ADMIN")
    def excluir_usuario(id):
        usuario = User.query.get_or_404(id)

        if usuario.email == usuario_logado_email():
            return redirect(url_for("listar_usuarios"))

        usuario.ativo = False
        db.session.commit()
        return redirect(url_for("listar_usuarios"))

    @usuarios_bp.route("/minha_conta", methods=["GET", "POST"])
    @login_required
    def minha_conta():
        user = User.query.filter_by(email=session.get("usuario")).first()
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if request.method == "POST":
            senha_atual = request.form.get("senha_atual")
            nova_senha = request.form.get("nova_senha")
            confirmar_senha = request.form.get("confirmar_senha")

            if (
                not (senha_atual or "").strip()
                or not (nova_senha or "").strip()
                or not (confirmar_senha or "").strip()
            ):
                return render_template(
                    "usuario/minha_conta.html",
                    erro="Preencha todos os campos."
                )

            if not user.senha or not check_password_hash(user.senha, senha_atual):
                return render_template(
                    "usuario/minha_conta.html",
                    erro="Senha atual incorreta."
                )

            if nova_senha != confirmar_senha:
                return render_template(
                    "usuario/minha_conta.html",
                    erro="A nova senha e a confirmacao nao conferem."
                )

            user.senha = generate_password_hash(nova_senha)
            db.session.commit()

            return render_template(
                "usuario/minha_conta.html",
                mensagem="Senha alterada com sucesso."
            )

        return render_template("usuario/minha_conta.html")

    return usuarios_bp
