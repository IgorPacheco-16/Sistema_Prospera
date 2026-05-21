from werkzeug.security import check_password_hash

from database.models import db, PasswordResetToken, User


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


def test_esqueci_senha_chama_servico_de_email(client, app, monkeypatch):
    import app as app_module

    chamadas = []

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas.append({
            "destinatarios": destinatarios,
            "assunto": assunto,
            "texto": texto,
            "html": html,
        })

        class Resultado:
            enviado = True

        return Resultado()

    monkeypatch.setattr(app_module.security_module, "enviar_email", enviar_email_fake)

    resposta = client.post("/esqueci_senha", data={"email": "admin@teste.com"})

    token = PasswordResetToken.query.join(User).filter(User.email == "admin@teste.com").first()
    assert resposta.status_code == 200
    assert token is not None
    assert chamadas
    assert chamadas[0]["destinatarios"] == ["admin@teste.com"]
    assert chamadas[0]["assunto"] == "Redefinicao de senha - Sistema OP"
    assert "Codigo:" in chamadas[0]["texto"]
