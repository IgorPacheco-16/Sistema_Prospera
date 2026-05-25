from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from database.models import CadastroPendente, db, PasswordResetToken, User
from tempo import agora_brasilia


def configurar_email_fake(monkeypatch):
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
    return chamadas


def codigo_enviado(chamadas):
    texto = chamadas[-1]["texto"]
    return texto.split("Codigo: ", 1)[1].splitlines()[0].strip()


def iniciar_cadastro(client, monkeypatch, email="cadastro@teste.com"):
    chamadas = configurar_email_fake(monkeypatch)
    resposta = client.post("/criar_conta", data={"email": email})
    return resposta, chamadas


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


def test_link_criar_conta_aparece_no_login(client):
    resposta = client.get("/")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Criar conta" in html
    assert "/criar_conta" in html
    assert "Mostrar" in html


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


def test_criar_conta_email_ja_cadastrado_mostra_aviso(client):
    resposta = client.post("/criar_conta", data={"email": "admin@teste.com"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Este e-mail já está cadastrado." in html


def test_cadastro_novo_envia_codigo(client, monkeypatch):
    resposta, chamadas = iniciar_cadastro(client, monkeypatch)

    cadastro = CadastroPendente.query.filter_by(email="cadastro@teste.com").first()
    codigo = codigo_enviado(chamadas)

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/criar_conta/codigo")
    assert cadastro is not None
    assert cadastro.codigo_hash != codigo
    assert check_password_hash(cadastro.codigo_hash, codigo)
    assert chamadas[0]["destinatarios"] == ["cadastro@teste.com"]
    assert chamadas[0]["assunto"] == "Codigo de verificacao - Sistema OP"


def test_codigo_correto_permite_avancar(client, monkeypatch):
    iniciar_cadastro(client, monkeypatch)
    chamadas = configurar_email_fake(monkeypatch)
    # Reenvia para ter um codigo conhecido nas chamadas atuais.
    client.post("/criar_conta", data={"email": "cadastro@teste.com"})
    codigo = codigo_enviado(chamadas)

    resposta = client.post("/criar_conta/codigo", data={"codigo": codigo})
    cadastro = CadastroPendente.query.filter_by(email="cadastro@teste.com").first()

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/criar_conta/finalizar")
    assert cadastro.verificado is True


def test_codigo_expirado_nao_permite_avancar(client):
    cadastro = CadastroPendente(
        email="expirado@teste.com",
        codigo_hash=generate_password_hash("123456"),
        expira_em=agora_brasilia() - timedelta(minutes=1),
    )
    db.session.add(cadastro)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["cadastro_email"] = "expirado@teste.com"

    resposta = client.post("/criar_conta/codigo", data={"codigo": "123456"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Código inválido ou expirado." in html
    assert CadastroPendente.query.filter_by(email="expirado@teste.com").first() is None


def test_codigo_errado_incrementa_tentativas_e_bloqueia(client):
    cadastro = CadastroPendente(
        email="tentativas@teste.com",
        codigo_hash=generate_password_hash("123456"),
        expira_em=agora_brasilia() + timedelta(minutes=15),
    )
    db.session.add(cadastro)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["cadastro_email"] = "tentativas@teste.com"

    resposta = None
    for _ in range(5):
        resposta = client.post("/criar_conta/codigo", data={"codigo": "000000"})

    db.session.refresh(cadastro)
    html = resposta.get_data(as_text=True)

    assert cadastro.tentativas == 5
    assert "Muitas tentativas incorretas. Solicite um novo código." in html


def test_usuario_criado_por_cadastro_fica_setor_ativo_e_senha_hasheada(
    client,
    monkeypatch,
    setores,
):
    _, chamadas = iniciar_cadastro(client, monkeypatch, email="setor.novo@teste.com")
    codigo = codigo_enviado(chamadas)
    client.post("/criar_conta/codigo", data={"codigo": codigo})

    resposta = client.post("/criar_conta/finalizar", data={
        "nome": "Setor Novo",
        "setor": str(setores["Acabamento"].id),
        "senha": "senha-segura",
        "confirmar_senha": "senha-segura",
    })

    usuario = User.query.filter_by(email="setor.novo@teste.com").first()

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")
    assert usuario is not None
    assert usuario.nome == "Setor Novo"
    assert usuario.tipo == "SETOR"
    assert usuario.tipo not in {"ADMIN", "PCP", "ATENDENTE", "ESPECTADOR"}
    assert usuario.setor_id == setores["Acabamento"].id
    assert usuario.ativo is True
    assert usuario.senha != "senha-segura"
    assert check_password_hash(usuario.senha, "senha-segura")


def test_cadastro_nao_permite_finalizar_sem_setor_existente(client, monkeypatch):
    _, chamadas = iniciar_cadastro(client, monkeypatch, email="sem.setor@teste.com")
    codigo = codigo_enviado(chamadas)
    client.post("/criar_conta/codigo", data={"codigo": codigo})

    resposta = client.post("/criar_conta/finalizar", data={
        "nome": "Sem Setor",
        "setor": "999999",
        "senha": "senha-segura",
        "confirmar_senha": "senha-segura",
    })
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Informe um setor válido." in html
    assert User.query.filter_by(email="sem.setor@teste.com").first() is None


def test_botao_mostrar_senha_aparece_nas_telas_de_senha(client, login_as):
    login = client.get("/").get_data(as_text=True)
    assert "Mostrar" in login

    with client.session_transaction() as sess:
        sess["reset_email"] = "admin@teste.com"
    redefinir = client.get("/redefinir_senha").get_data(as_text=True)
    assert redefinir.count("Mostrar") >= 2

    user_tmp = User.query.filter_by(email="novo@teste.com").first()
    with client.session_transaction() as sess:
        sess["tmp_user"] = user_tmp.id
    definir = client.get("/definir_senha").get_data(as_text=True)
    assert definir.count("Mostrar") >= 2

    login_as("ADMIN")
    criar_usuario = client.get("/criar_usuario").get_data(as_text=True)
    minha_conta = client.get("/minha_conta").get_data(as_text=True)
    usuario = User.query.filter_by(email="pcp@teste.com").first()
    editar_usuario = client.get(f"/usuarios/{usuario.id}/editar").get_data(as_text=True)

    assert "Mostrar" in criar_usuario
    assert minha_conta.count("Mostrar") >= 3
    assert "Mostrar" in editar_usuario

    cadastro = CadastroPendente(
        email="toggle@teste.com",
        codigo_hash=generate_password_hash("123456"),
        expira_em=agora_brasilia() + timedelta(minutes=15),
        verificado=True,
    )
    db.session.add(cadastro)
    db.session.commit()
    with client.session_transaction() as sess:
        sess["cadastro_email"] = "toggle@teste.com"
    finalizar = client.get("/criar_conta/finalizar").get_data(as_text=True)
    assert finalizar.count("Mostrar") >= 2


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
    codigo = codigo_enviado(chamadas)
    assert resposta.status_code == 200
    assert token is not None
    assert chamadas
    assert chamadas[0]["destinatarios"] == ["admin@teste.com"]
    assert chamadas[0]["assunto"] == "Redefinicao de senha - Sistema OP"
    assert "Codigo:" in chamadas[0]["texto"]

    resposta_redefinir = client.post("/redefinir_senha", data={
        "codigo": codigo,
        "nova_senha": "nova-recuperada",
        "confirmar_senha": "nova-recuperada",
    })
    usuario = User.query.filter_by(email="admin@teste.com").first()

    assert resposta_redefinir.status_code == 302
    assert check_password_hash(usuario.senha, "nova-recuperada")
