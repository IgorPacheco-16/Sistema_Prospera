from werkzeug.security import check_password_hash, generate_password_hash

from database.models import db, User


def test_criar_usuario_pcp_pode_ter_setor_vinculado(client, login_as, setores):
    login_as("ADMIN")

    resposta = client.post("/criar_usuario", data={
        "nome": "PCP Setor",
        "email": "pcp.setor@teste.com",
        "tipo": "PCP",
        "setor": str(setores["PCP"].id),
        "senha": "123",
    })

    usuario = User.query.filter_by(email="pcp.setor@teste.com").first()
    assert resposta.status_code == 200
    assert usuario is not None
    assert usuario.nome == "PCP Setor"
    assert usuario.tipo == "PCP"
    assert usuario.setor_id == setores["PCP"].id
    assert usuario.ativo is True


def test_criar_usuario_atendente_pode_ficar_sem_setor(client, login_as):
    login_as("ADMIN")

    resposta = client.post("/criar_usuario", data={
        "nome": "Atendente Sem Setor",
        "email": "atendente.sem.setor@teste.com",
        "tipo": "ATENDENTE",
        "setor": "",
        "senha": "123",
    })

    usuario = User.query.filter_by(email="atendente.sem.setor@teste.com").first()
    assert resposta.status_code == 200
    assert usuario is not None
    assert usuario.nome == "Atendente Sem Setor"
    assert usuario.tipo == "ATENDENTE"
    assert usuario.setor_id is None


def test_admin_consegue_criar_usuario_espectador(client, login_as):
    login_as("ADMIN")

    resposta = client.post("/criar_usuario", data={
        "nome": "Espectador Novo",
        "email": "espectador.novo@teste.com",
        "tipo": "ESPECTADOR",
        "setor": "",
        "senha": "123",
    })

    usuario = User.query.filter_by(email="espectador.novo@teste.com").first()

    assert resposta.status_code == 200
    assert usuario is not None
    assert usuario.nome == "Espectador Novo"
    assert usuario.tipo == "ESPECTADOR"
    assert usuario.setor_id is None


def test_criar_usuario_setor_continua_exigindo_setor(client, login_as):
    login_as("ADMIN")

    resposta = client.post("/criar_usuario", data={
        "nome": "Setor Sem Setor",
        "email": "setor.sem.setor@teste.com",
        "tipo": "SETOR",
        "setor": "",
        "senha": "123",
    })

    html = resposta.get_data(as_text=True)
    usuario = User.query.filter_by(email="setor.sem.setor@teste.com").first()
    assert resposta.status_code == 200
    assert usuario is None
    assert "Informe o setor para usuarios do tipo SETOR." in html


def test_criar_usuario_exige_nome(client, login_as):
    login_as("ADMIN")

    resposta = client.post("/criar_usuario", data={
        "nome": "",
        "email": "sem.nome@teste.com",
        "tipo": "ATENDENTE",
        "setor": "",
        "senha": "123",
    })

    assert resposta.status_code == 200
    assert User.query.filter_by(email="sem.nome@teste.com").first() is None
    assert "Informe o nome." in resposta.get_data(as_text=True)


def test_admin_lista_usuarios(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/usuarios")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "admin@teste.com" in html
    assert "pcp@teste.com" in html


def test_admin_lista_usuarios_pendentes_com_acao_de_aprovar(client, login_as, setores):
    usuario = User(
        email="pendente@teste.com",
        senha=generate_password_hash("123"),
        tipo="SETOR",
        setor_id=setores["Acabamento"].id,
        ativo=False,
    )
    db.session.add(usuario)
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/usuarios")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Usuarios aguardando aprovacao" in html
    assert "Aguardando aprovacao / inativo" in html
    assert "Aprovar cadastro" in html


def test_nao_admin_nao_aprova_usuario_pendente(client, login_as, setores):
    usuario = User(
        email="pendente@teste.com",
        senha=generate_password_hash("123"),
        tipo="SETOR",
        setor_id=setores["Acabamento"].id,
        ativo=False,
    )
    db.session.add(usuario)
    db.session.commit()
    login_as("PCP")

    resposta = client.post(f"/usuarios/{usuario.id}/alternar_status")
    db.session.refresh(usuario)

    assert resposta.status_code == 403
    assert usuario.ativo is False


def test_nao_admin_nao_acessa_gestao_de_usuarios(client, login_as):
    login_as("PCP")

    resposta = client.get("/usuarios")

    assert resposta.status_code == 403


def test_admin_edita_usuario_igor_para_pcp_setor_pcp_ativo(client, login_as, setores):
    usuario = User(
        email="igor@prosperaproducoes.com.br",
        senha=generate_password_hash("antiga"),
        tipo="ATENDENTE",
        setor_id=None,
        ativo=False
    )
    db.session.add(usuario)
    db.session.commit()
    senha_anterior = usuario.senha
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{usuario.id}/editar", data={
        "nome": "Igor PCP",
        "email": "igor@prosperaproducoes.com.br",
        "tipo": "PCP",
        "setor": str(setores["PCP"].id),
        "ativo": "on",
        "nova_senha": "",
    })

    db.session.refresh(usuario)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/usuarios")
    assert usuario.nome == "Igor PCP"
    assert usuario.tipo == "PCP"
    assert usuario.setor_id == setores["PCP"].id
    assert usuario.ativo is True
    assert usuario.senha == senha_anterior


def test_admin_redefine_senha_opcionalmente(client, login_as):
    usuario = User.query.filter_by(email="pcp@teste.com").first()
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{usuario.id}/editar", data={
        "nome": usuario.nome or "PCP",
        "email": usuario.email,
        "tipo": usuario.tipo,
        "setor": "",
        "ativo": "on",
        "nova_senha": "nova123",
    })

    db.session.refresh(usuario)
    assert resposta.status_code == 302
    assert check_password_hash(usuario.senha, "nova123")


def test_admin_edita_nome_do_usuario_sem_alterar_senha(client, login_as):
    usuario = User.query.filter_by(email="pcp@teste.com").first()
    senha_anterior = usuario.senha
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{usuario.id}/editar", data={
        "nome": "PCP Renomeado",
        "email": usuario.email,
        "tipo": usuario.tipo,
        "setor": "",
        "ativo": "on",
        "nova_senha": "",
    })

    db.session.refresh(usuario)
    assert resposta.status_code == 302
    assert usuario.nome == "PCP Renomeado"
    assert usuario.senha == senha_anterior


def test_admin_nao_edita_usuario_sem_nome(client, login_as):
    usuario = User.query.filter_by(email="pcp@teste.com").first()
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{usuario.id}/editar", data={
        "nome": "",
        "email": usuario.email,
        "tipo": usuario.tipo,
        "setor": "",
        "ativo": "on",
        "nova_senha": "",
    })

    assert resposta.status_code == 200
    assert "Informe o nome." in resposta.get_data(as_text=True)


def test_desativar_usuario_bloqueia_login(client, login_as):
    usuario = User.query.filter_by(email="pcp@teste.com").first()
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{usuario.id}/alternar_status")
    db.session.refresh(usuario)

    assert resposta.status_code == 302
    assert usuario.ativo is False

    with client.session_transaction() as sess:
        sess.clear()

    resposta_login = client.post("/", data={
        "email": "pcp@teste.com",
        "senha": "123",
    })
    html = resposta_login.get_data(as_text=True)

    assert resposta_login.status_code == 200
    assert "Sua conta foi criada e está aguardando aprovação de um administrador." in html


def test_excluir_usuario_desativa_sem_apagar(client, login_as):
    usuario = User.query.filter_by(email="pcp@teste.com").first()
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{usuario.id}/excluir")
    usuario_persistido = db.session.get(User, usuario.id)

    assert resposta.status_code == 302
    assert usuario_persistido is not None
    assert usuario_persistido.ativo is False


def test_nao_permite_excluir_proprio_admin(client, login_as):
    admin = User.query.filter_by(email="admin@teste.com").first()
    login_as("ADMIN")

    resposta = client.post(f"/usuarios/{admin.id}/excluir")
    db.session.refresh(admin)

    assert resposta.status_code == 302
    assert admin.ativo is True
