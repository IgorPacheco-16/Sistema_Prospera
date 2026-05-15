from werkzeug.security import check_password_hash

from database.models import db, User


def test_login_valido_redireciona_para_dashboard(client):
    resposta = client.post("/", data={
        "email": "admin@teste.com",
        "senha": "123",
    })

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/dashboard")

    with client.session_transaction() as sess:
        assert sess["usuario"] == "admin@teste.com"
        assert sess["tipo"] == "ADMIN"


def test_login_invalido_mostra_erro(client):
    resposta = client.post("/", data={
        "email": "admin@teste.com",
        "senha": "senha-errada",
    })

    assert resposta.status_code == 200
    assert b"Email ou senha invalidos" in resposta.data


def test_rota_protegida_sem_login_redireciona_para_login(client):
    resposta = client.get("/dashboard")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")


def test_definir_senha_para_usuario_temporario(client, app):
    user = User.query.filter_by(email="novo@teste.com").first()

    with client.session_transaction() as sess:
        sess["tmp_user"] = user.id

    resposta = client.post("/definir_senha", data={
        "senha": "nova-senha",
        "confirmar_senha": "nova-senha",
    })

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")

    db.session.refresh(user)
    assert user.ativo is True
    assert check_password_hash(user.senha, "nova-senha")
