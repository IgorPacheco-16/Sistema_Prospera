from datetime import timedelta

from database.models import db, Notificacao, OP, OPSetor, Tarefa, User
from tempo import hoje_brasilia


class ResultadoEmail:
    enviado = True
    erro = None


def criar_usuario(email, setor, nome=None, tipo="SETOR", ativo=True):
    usuario = User(
        nome=nome,
        email=email,
        senha="123",
        tipo=tipo,
        setor_id=setor.id,
        ativo=ativo,
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def atribuir_responsaveis(tarefa, responsaveis):
    tarefa.responsaveis = responsaveis
    db.session.commit()
    return tarefa


def emails_responsaveis(tarefa):
    return [usuario.email for usuario in tarefa.responsaveis]


def test_criar_tarefa_sem_responsaveis_mantem_notificacao_do_setor(client, login_as, op_com_setor):
    op, setor = op_com_setor
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={"nome": "Tarefa geral", "prazo": "", "responsaveis": ""},
        headers={"Referer": f"/op/{op.id}"}
    )

    tarefa = Tarefa.query.filter_by(nome="Tarefa geral").first()
    assert resposta.status_code == 302
    assert emails_responsaveis(tarefa) == []
    assert Notificacao.query.filter_by(
        usuario="SETOR",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_criada",
    ).first()


def test_criar_tarefa_com_um_responsavel_salva_e_notifica_apenas_ele(client, login_as, op_com_setor):
    op, setor = op_com_setor
    responsavel = criar_usuario("responsavel@teste.com", setor, nome="Responsavel Um")
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={
            "nome": "Tarefa individual",
            "prazo": "",
            "responsaveis": [str(responsavel.id)],
        },
        headers={"Referer": f"/op/{op.id}"}
    )

    tarefa = Tarefa.query.filter_by(nome="Tarefa individual").first()
    assert resposta.status_code == 302
    assert emails_responsaveis(tarefa) == ["responsavel@teste.com"]
    assert Notificacao.query.filter_by(
        usuario="responsavel@teste.com",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_criada",
    ).first()
    assert not Notificacao.query.filter_by(
        usuario="SETOR",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_criada",
    ).first()


def test_criar_tarefa_com_quatro_responsaveis(client, login_as, op_com_setor):
    op, setor = op_com_setor
    responsaveis = [
        criar_usuario(f"resp{indice}@teste.com", setor, nome=f"Resp {indice}")
        for indice in range(4)
    ]
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={
            "nome": "Tarefa quatro",
            "responsaveis": [str(usuario.id) for usuario in responsaveis],
        },
        headers={"Referer": f"/op/{op.id}"}
    )

    tarefa = Tarefa.query.filter_by(nome="Tarefa quatro").first()
    assert resposta.status_code == 302
    assert len(tarefa.responsaveis) == 4


def test_bloqueia_cinco_responsaveis(client, login_as, op_com_setor):
    op, setor = op_com_setor
    responsaveis = [
        criar_usuario(f"resp.cinco.{indice}@teste.com", setor, nome=f"Resp Cinco {indice}")
        for indice in range(5)
    ]
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={
            "nome": "Tarefa cinco",
            "responsaveis": [str(usuario.id) for usuario in responsaveis],
        },
        headers={"Referer": f"/op/{op.id}"}
    )

    assert resposta.status_code == 400
    assert "maximo 4 responsaveis" in resposta.get_data(as_text=True)
    assert Tarefa.query.filter_by(nome="Tarefa cinco").first() is None


def test_nao_permite_responsavel_de_outro_setor(client, login_as, op_com_setor, setores):
    op, setor = op_com_setor
    responsavel_outro_setor = criar_usuario(
        "responsavel.pcp@teste.com",
        setores["PCP"],
        nome="Responsavel PCP",
    )
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={
            "nome": "Tarefa invalida",
            "responsaveis": [str(responsavel_outro_setor.id)],
        },
        headers={"Referer": f"/op/{op.id}"}
    )

    assert resposta.status_code == 400
    assert Tarefa.query.filter_by(nome="Tarefa invalida").first() is None


def test_nao_permite_responsavel_inativo(client, login_as, op_com_setor):
    op, setor = op_com_setor
    responsavel_inativo = criar_usuario(
        "responsavel.inativo@teste.com",
        setor,
        nome="Responsavel Inativo",
        ativo=False,
    )
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={
            "nome": "Tarefa inativa",
            "responsaveis": [str(responsavel_inativo.id)],
        },
        headers={"Referer": f"/op/{op.id}"}
    )

    assert resposta.status_code == 400
    assert Tarefa.query.filter_by(nome="Tarefa inativa").first() is None


def test_responsaveis_aparecem_ordenados_por_nome(client, login_as, tarefa):
    zelia = criar_usuario("zelia@teste.com", tarefa.setor, nome="Zelia")
    ana = criar_usuario("ana@teste.com", tarefa.setor, nome="Ana")
    atribuir_responsaveis(tarefa, [zelia, ana])
    login_as("ADMIN")

    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)

    assert html.index("Ana") < html.index("Zelia")


def test_modal_responsaveis_usa_controle_compacto(client, login_as, tarefa):
    login_as("ADMIN")

    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)

    assert "task-responsavel-select" in html
    assert "task-assignee-picker" in html
    assert "task-assignee-count" in html
    assert "Geral do setor" in html


def test_qualquer_usuario_do_setor_consegue_iniciar_e_entregar_com_responsaveis(client, login_as, tarefa):
    primeiro = criar_usuario("primeiro.fluxo@teste.com", tarefa.setor, nome="Primeiro")
    segundo = criar_usuario("segundo.fluxo@teste.com", tarefa.setor, nome="Segundo")
    atribuir_responsaveis(tarefa, [primeiro, segundo])

    login_as("SETOR", email=segundo.email, setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    assert resposta.status_code == 302

    login_as("SETOR", email=primeiro.email, setor_id=tarefa.setor_id)
    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    assert resposta.status_code == 302

    login_as("ADMIN")
    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)

    assert resposta.status_code == 302
    assert tarefa.validado is True
    assert tarefa.status == "ENTREGUE"


def test_usuario_mesmo_setor_nao_marcado_movimenta_por_vinculo_do_setor(client, login_as, tarefa):
    responsavel = criar_usuario("responsavel.bloqueio@teste.com", tarefa.setor)
    colega = criar_usuario("colega.bloqueio@teste.com", tarefa.setor)
    atribuir_responsaveis(tarefa, [responsavel])
    login_as("SETOR", email=colega.email, setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)

    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"


def test_admin_continua_podendo_movimentar_tarefa_com_responsaveis(client, login_as, tarefa):
    responsavel = criar_usuario("responsavel.admin@teste.com", tarefa.setor)
    atribuir_responsaveis(tarefa, [responsavel])
    login_as("ADMIN")

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)

    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"


def test_atraso_com_responsaveis_notifica_e_envia_email_apenas_para_eles(app, setores, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    setor = setores["Acabamento"]
    ana = criar_usuario("ana.atraso@teste.com", setor, nome="Ana")
    zelia = criar_usuario("zelia.atraso@teste.com", setor, nome="Zelia")
    op = OP(
        nome="OP Atraso Responsaveis",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Tarefa atraso responsaveis",
        prazo=hoje_brasilia() - timedelta(days=1),
        validado=False,
    )
    db.session.add(tarefa)
    db.session.flush()
    tarefa.responsaveis = [zelia, ana]
    db.session.commit()

    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas.append(destinatarios)
        return ResultadoEmail()

    monkeypatch.setattr(services, "enviar_email_smtp", enviar_email_fake)

    resumo = services.verificar_atrasos()
    db.session.commit()

    notificacoes = Notificacao.query.filter_by(
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_atrasada",
    ).order_by(Notificacao.usuario).all()
    assert resumo["notificacoes_criadas"] == 2
    assert [n.usuario for n in notificacoes] == [
        "ana.atraso@teste.com",
        "zelia.atraso@teste.com",
    ]
    assert chamadas == [["ana.atraso@teste.com", "zelia.atraso@teste.com"]]


def test_tarefa_sem_responsaveis_continua_enviando_email_para_setor(app, setores, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    setor = setores["Acabamento"]
    op = OP(nome="OP Atraso Setor", status="EM ANDAMENTO", atendente="atendente@teste.com")
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    db.session.add(Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Tarefa atraso setor",
        prazo=hoje_brasilia() - timedelta(days=1),
        validado=False,
    ))
    db.session.commit()

    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas.append(destinatarios)
        return ResultadoEmail()

    monkeypatch.setattr(services, "enviar_email_smtp", enviar_email_fake)

    services.verificar_atrasos()

    assert chamadas
    assert "setor@teste.com" in chamadas[0]
    assert "atendente@teste.com" in chamadas[0]
    assert "pcp@teste.com" in chamadas[0]


def test_detalhe_kanban_calendario_e_slides_exibem_responsaveis(client, login_as, tarefa):
    ana = criar_usuario("ana.telas@teste.com", tarefa.setor, nome="Ana Responsavel")
    bia = criar_usuario("bia.telas@teste.com", tarefa.setor, nome="Bia Responsavel")
    atribuir_responsaveis(tarefa, [bia, ana])
    tarefa.prazo = hoje_brasilia()
    db.session.commit()
    login_as("ADMIN")

    detalhe = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)
    kanban = client.get("/kanban").get_data(as_text=True)
    calendario = client.get("/calendario").get_data(as_text=True)
    slides = client.get("/api/slides").get_json()

    assert "Ana Responsavel" in detalhe
    assert "Bia Responsavel" in detalhe
    assert "Ana Responsavel" in kanban
    assert "Ana Responsavel" in calendario
    itens = [
        item
        for categoria in slides["categorias"].values()
        for item in categoria
    ]
    assert any(
        item["responsavel"] == "Ana Responsavel, Bia Responsavel"
        for item in itens
    )


def test_slides_retorna_geral_do_setor_quando_sem_responsaveis(client, login_as, tarefa):
    tarefa.prazo = hoje_brasilia()
    db.session.commit()
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    itens = dados["categorias"]["hoje"]

    assert any(item["responsavel"] == "Geral do setor" for item in itens)


def test_criar_op_lista_setores_em_ordem_alfabetica(client, login_as):
    login_as("ATENDENTE")

    html = client.get("/criar_op").get_data(as_text=True)

    assert html.index("Acabamento") < html.index("Atendimento") < html.index("PCP")
