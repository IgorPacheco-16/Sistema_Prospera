from werkzeug.security import check_password_hash

from database.models import db, User


def test_criar_admin_cria_primeiro_admin_sem_senha_padrao(app):
    User.query.delete()
    db.session.commit()

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=[
        "criar-admin",
        "--email",
        "Primeiro.Admin@Teste.com",
        "--nome",
        "Primeiro Admin",
        "--senha",
        "SenhaSegura123",
    ])

    usuario = User.query.filter_by(email="primeiro.admin@teste.com").first()
    assert resultado.exit_code == 0
    assert usuario is not None
    assert usuario.nome == "Primeiro Admin"
    assert usuario.tipo == "ADMIN"
    assert usuario.ativo is True
    assert not check_password_hash(usuario.senha, "123")
    assert check_password_hash(usuario.senha, "SenhaSegura123")


def test_criar_admin_bloqueia_quando_ja_existe_admin_ativo(app):
    runner = app.test_cli_runner()
    resultado = runner.invoke(args=[
        "criar-admin",
        "--email",
        "outro@teste.com",
        "--nome",
        "Outro Admin",
        "--senha",
        "SenhaSegura123",
    ])

    assert resultado.exit_code != 0
    assert "Ja existe um administrador ativo" in resultado.output
