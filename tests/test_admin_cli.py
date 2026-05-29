from werkzeug.security import check_password_hash

from database.models import db, Setor, User


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


def test_seed_usuarios_teste_cria_usuarios_locais_idempotente(app, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AMBIENTE", "test")

    runner = app.test_cli_runner()
    primeiro = runner.invoke(args=["seed", "usuarios-teste"])
    segundo = runner.invoke(args=["seed", "usuarios-teste"])

    setores = Setor.query.order_by(Setor.nome).all()
    usuarios_locais = User.query.filter(User.email.endswith("@local.test")).all()

    assert primeiro.exit_code == 0
    assert segundo.exit_code == 0
    assert "Senha padrao: teste123" in primeiro.output
    assert "admin.teste@local.test" in primeiro.output
    assert len(usuarios_locais) == len(setores) + 4

    for email, tipo in [
        ("admin.teste@local.test", "ADMIN"),
        ("pcp.teste@local.test", "PCP"),
        ("atendente.teste@local.test", "ATENDENTE"),
        ("espectador.teste@local.test", "ESPECTADOR"),
    ]:
        usuario = User.query.filter_by(email=email).first()
        assert usuario is not None
        assert usuario.tipo == tipo
        assert usuario.ativo is True
        assert usuario.setor_id is None
        assert check_password_hash(usuario.senha, "teste123")

    usuarios_setor = [
        usuario
        for usuario in usuarios_locais
        if usuario.tipo == "SETOR"
    ]
    assert len(usuarios_setor) == len(setores)
    assert {usuario.setor_id for usuario in usuarios_setor} == {
        setor.id for setor in setores
    }
    assert all(usuario.ativo is True for usuario in usuarios_setor)
    assert all(check_password_hash(usuario.senha, "teste123") for usuario in usuarios_setor)


def test_seed_usuarios_teste_bloqueia_production(app, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AMBIENTE", "production")

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["seed", "usuarios-teste"])

    assert resultado.exit_code != 0
    assert "bloqueado: APP_ENV=production" in resultado.output
    assert User.query.filter_by(email="admin.teste@local.test").first() is None
