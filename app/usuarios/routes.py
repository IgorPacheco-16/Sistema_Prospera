from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import db, Setor, User


def create_usuarios_blueprint(login_required, tipos_permitidos, normalizar_email):
    usuarios_bp = Blueprint("usuarios", __name__)

    @usuarios_bp.route("/criar_usuario", methods=["GET", "POST"])
    @tipos_permitidos("ADMIN")
    def criar_usuario():
        setores = Setor.query.all()
        tipos = ["ADMIN", "ATENDENTE", "PCP", "SETOR"]

        if request.method == "POST":
            email = normalizar_email(request.form.get("email"))
            tipo = request.form.get("tipo")
            setor_id = request.form.get("setor")
            senha = request.form.get("senha")

            if not email:
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Informe o email."
                )

            if tipo not in tipos:
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Tipo de usuario invalido."
                )

            if User.query.filter_by(email=email).first():
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Ja existe um usuario com este email."
                )

            if not (senha or "").strip():
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Informe a senha inicial."
                )

            if tipo == "SETOR" and not setor_id:
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Informe o setor para usuarios do tipo SETOR."
                )

            try:
                setor_id_convertido = int(setor_id) if tipo == "SETOR" and setor_id else None
            except ValueError:
                setor_id_convertido = None

            if tipo == "SETOR" and not setor_id_convertido:
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Setor invalido."
                )

            if setor_id_convertido and not db.session.get(Setor, setor_id_convertido):
                return render_template(
                    "usuario/criar_usuario.html",
                    setores=setores,
                    tipos=tipos,
                    erro="Setor invalido."
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
                setores=setores,
                tipos=tipos,
                mensagem="Usuario criado com sucesso."
            )

        return render_template("usuario/criar_usuario.html", setores=setores, tipos=tipos)

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
