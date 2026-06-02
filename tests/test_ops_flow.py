from datetime import date, datetime, timedelta

from database.models import db, Notificacao, OP, OPSetor, Tarefa, User
from tempo import hoje_brasilia


EMAIL_ENV_KEYS = [
    "MAIL_SERVER",
    "MAIL_PORT",
    "MAIL_USERNAME",
    "MAIL_PASSWORD",
    "MAIL_DEFAULT_SENDER",
    "MAIL_USE_TLS",
    "MAIL_USE_SSL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_USER",
    "EMAIL_USERNAME",
    "EMAIL_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_USE_TLS",
    "EMAIL_USE_SSL",
]


def limpar_env_email(monkeypatch):
    for chave in EMAIL_ENV_KEYS:
        monkeypatch.delenv(chave, raising=False)


def limpar_config_email(flask_app):
    for chave in [
        "MAIL_SERVER",
        "MAIL_PORT",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
        "MAIL_USE_TLS",
        "MAIL_USE_SSL",
    ]:
        flask_app.config.pop(chave, None)


def criar_op_dashboard(nome, setor=None, cliente=None, status="EM ANDAMENTO"):
    op = OP(
        nome=nome,
        status=status,
        atendente="atendente@teste.com",
        cliente=cliente,
        prazo_final=date(2026, 5, 20),
    )
    db.session.add(op)
    db.session.flush()
    if setor:
        db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    return op


def test_dashboard_carrega_logado(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/dashboard")

    assert resposta.status_code == 200


def test_dashboard_mostra_cliente_nos_cards(client, login_as, setores):
    setor = setores["Acabamento"]
    op_com_cliente = OP(
        nome="OP Dashboard Cliente",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        cliente="Cliente Dashboard",
    )
    op_sem_cliente = OP(
        nome="OP Dashboard Sem Cliente",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        cliente=None,
    )
    db.session.add_all([op_com_cliente, op_sem_cliente])
    db.session.flush()
    db.session.add_all([
        OPSetor(op_id=op_com_cliente.id, setor_id=setor.id),
        OPSetor(op_id=op_sem_cliente.id, setor_id=setor.id),
    ])
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Cliente: Cliente Dashboard" in html
    assert "Cliente: Não informado" in html


def test_dashboard_busca_por_cliente_retorna_op_correta(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_dashboard("OP Campanha Institucional", setor=setor, cliente="Cliente Alvo")
    criar_op_dashboard("OP Campanha Varejo", setor=setor, cliente="Cliente Diferente")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=Alvo")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Campanha Institucional" in html
    assert "Cliente: Cliente Alvo" in html
    assert "OP Campanha Varejo" not in html


def test_dashboard_busca_parcial_por_cliente_funciona(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_dashboard("OP Evento Corporativo", setor=setor, cliente="Nestle Brasil")
    criar_op_dashboard("OP Evento Interno", setor=setor, cliente="Outro Cliente")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=nest")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Evento Corporativo" in html
    assert "Cliente: Nestle Brasil" in html
    assert "OP Evento Interno" not in html


def test_dashboard_busca_por_cliente_e_case_insensitive(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_dashboard("OP Stand Feira", setor=setor, cliente="MEGACORP")
    criar_op_dashboard("OP Stand Concorrente", setor=setor, cliente="Cliente Concorrente")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=megacorp")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Stand Feira" in html
    assert "Cliente: MEGACORP" in html
    assert "OP Stand Concorrente" not in html


def test_dashboard_busca_por_nome_da_op_continua_funcionando(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_dashboard("OP Nome Encontravel", setor=setor, cliente="Cliente Um")
    criar_op_dashboard("OP Nome Fora", setor=setor, cliente="Cliente Dois")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=Nome%20Encontravel")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Nome Encontravel" in html
    assert "OP Nome Fora" not in html


def test_dashboard_busca_por_cliente_combinada_com_status(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_dashboard(
        "OP Cliente Status Finalizada",
        setor=setor,
        cliente="Cliente Status",
        status="FINALIZADA",
    )
    criar_op_dashboard(
        "OP Cliente Status Andamento",
        setor=setor,
        cliente="Cliente Status",
        status="EM ANDAMENTO",
    )
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=Cliente%20Status&status=FINALIZADA")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Cliente Status Finalizada" in html
    assert "OP Cliente Status Andamento" not in html


def test_dashboard_paginacao_preserva_busca_por_cliente(client, login_as, setores):
    setor = setores["Acabamento"]
    for indice in range(22):
        criar_op_dashboard(
            f"OP Paginado {indice:02d}",
            setor=setor,
            cliente="Cliente Paginado",
        )
    criar_op_dashboard("OP Cliente Excluido", setor=setor, cliente="Outro Cliente")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=Cliente%20Paginado")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count("Ver OP") == 18
    assert "OP Cliente Excluido" not in html
    assert 'href="/dashboard?page=2&amp;busca=Cliente+Paginado#ops-list"' in html

    segunda_pagina = client.get("/dashboard?busca=Cliente%20Paginado&page=2").get_data(as_text=True)
    assert segunda_pagina.count("Ver OP") == 4
    assert "OP Paginado 18" in segunda_pagina
    assert "OP Paginado 21" in segunda_pagina
    assert "OP Cliente Excluido" not in segunda_pagina


def test_dashboard_setor_nao_enxerga_op_de_outro_setor_por_busca_cliente(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    criar_op_dashboard("OP Cliente Permitido Setor", setor=acabamento, cliente="Cliente Restrito")
    criar_op_dashboard("OP Cliente Outro Setor", setor=pcp, cliente="Cliente Restrito")
    db.session.commit()
    login_as("SETOR", setor_id=acabamento.id)

    resposta = client.get("/dashboard?busca=Cliente%20Restrito")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Cliente Permitido Setor" in html
    assert "OP Cliente Outro Setor" not in html


def test_dashboard_cliente_vazio_ou_nulo_nao_quebra_busca(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_dashboard("OP Cliente Nulo", setor=setor, cliente=None)
    criar_op_dashboard("OP Cliente Vazio", setor=setor, cliente="")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=OP%20Cliente")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Cliente Nulo" in html
    assert "OP Cliente Vazio" in html


def test_dashboard_limita_listagem_a_dezoito_ops_por_pagina(client, login_as):
    for indice in range(25):
        db.session.add(OP(
            nome=f"OP Paginada {indice:02d}",
            status="EM ANDAMENTO",
            atendente="atendente@teste.com",
            prazo_final=date(2026, 5, 20),
        ))
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count("Ver OP") == 18
    assert "OP Paginada 00" in html
    assert "OP Paginada 17" in html
    assert "OP Paginada 18" not in html
    assert '<span class="page-link">1</span>' in html
    assert 'href="/dashboard?page=2#ops-list"' in html
    assert "Mostrando 1-18 de 25" in html


def test_dashboard_pagina_dois_mostra_proximas_ops(client, login_as):
    for indice in range(25):
        db.session.add(OP(
            nome=f"OP Segunda Pagina {indice:02d}",
            status="EM ANDAMENTO",
            atendente="atendente@teste.com",
            prazo_final=date(2026, 5, 20),
        ))
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?page=2")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count("Ver OP") == 7
    assert "OP Segunda Pagina 17" not in html
    assert "OP Segunda Pagina 18" in html
    assert "OP Segunda Pagina 24" in html
    assert 'href="/dashboard?page=1#ops-list"' in html
    assert '<span class="page-link">2</span>' in html
    assert "Mostrando 19-25 de 25" in html


def test_dashboard_paginacao_preserva_filtros(client, login_as):
    for indice in range(22):
        db.session.add(OP(
            nome=f"OP Nestle {indice:02d}",
            status="EM ANDAMENTO",
            atendente="atendente@teste.com",
            prazo_final=date(2026, 5, 20),
        ))
    db.session.add(OP(
        nome="OP Outro Cliente",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        prazo_final=date(2026, 5, 20),
    ))
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=Nestle")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count("Ver OP") == 18
    assert "OP Outro Cliente" not in html
    assert "page=2" in html
    assert "busca=Nestle" in html
    assert 'href="/dashboard?page=2&amp;busca=Nestle#ops-list"' in html

    segunda_pagina = client.get("/dashboard?busca=Nestle&page=2").get_data(as_text=True)
    assert segunda_pagina.count("Ver OP") == 4
    assert "OP Nestle 18" in segunda_pagina
    assert "OP Nestle 19" in segunda_pagina
    assert "OP Nestle 20" in segunda_pagina
    assert "OP Nestle 21" in segunda_pagina
    assert "OP Outro Cliente" not in segunda_pagina


def test_dashboard_paginacao_numerica_usa_reticencias(client, login_as):
    for indice in range(360):
        db.session.add(OP(
            nome=f"OP Muitas Paginas {indice:03d}",
            status="EM ANDAMENTO",
            atendente="atendente@teste.com",
            prazo_final=date(2026, 5, 20),
        ))
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?page=5")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert 'href="/dashboard?page=1#ops-list"' in html
    assert 'href="/dashboard?page=4#ops-list"' in html
    assert '<span class="page-link">5</span>' in html
    assert 'href="/dashboard?page=6#ops-list"' in html
    assert 'href="/dashboard?page=20#ops-list"' in html
    assert "&hellip;" in html


def test_dashboard_pagina_fora_do_intervalo_usa_ultima_pagina(client, login_as):
    for indice in range(25):
        db.session.add(OP(
            nome=f"OP Fora Intervalo {indice:02d}",
            status="EM ANDAMENTO",
            atendente="atendente@teste.com",
            prazo_final=date(2026, 5, 20),
        ))
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/dashboard?page=999")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Mostrando 19-25 de 25" in html
    assert '<span class="page-link">2</span>' in html


def test_dashboard_mostra_mensagem_sem_resultados(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/dashboard?busca=Inexistente")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Nenhuma OP encontrada com os filtros atuais." in html
    assert "Nenhum resultado" in html


def test_calendario_mostra_apenas_tarefas_pendentes_de_ops_em_andamento(client, login_as, setores):
    setor = setores["Acabamento"]
    prazo = hoje_brasilia() + timedelta(days=1)

    cenarios = [
        ("OP Em Andamento", "EM ANDAMENTO", False),
        ("OP Finalizada", "FINALIZADA", False),
        ("OP Arquivada", "ARQUIVADA", False),
        ("OP Validada", "EM ANDAMENTO", True),
    ]

    for nome, status, validado in cenarios:
        op = OP(nome=nome, status=status, atendente="atendente@teste.com")
        db.session.add(op)
        db.session.flush()
        db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
        db.session.add(Tarefa(
            op_id=op.id,
            setor_id=setor.id,
            nome=f"Tarefa {nome}",
            prazo=prazo,
            validado=validado,
            liberada=True
        ))

    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/calendario")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Em Andamento" in html
    assert "OP Finalizada" not in html
    assert "OP Arquivada" not in html
    assert "OP Validada" not in html


def test_criacao_de_op(client, login_as, setores):
    login_as("ATENDENTE")

    resposta = client.post("/criar_op", data={
        "nome": "OP Nova",
        "cliente": "Cliente Prospera",
        "prazo": "2026-05-20",
        "caminho_pasta": r"\\servidor\projetos\Cliente\OP123",
        "setores": [str(setores["Acabamento"].id)],
    })

    op = OP.query.filter_by(nome="OP Nova").first()
    assert resposta.status_code == 302
    assert op is not None
    assert op.criada_em is not None
    assert op.cliente == "Cliente Prospera"
    assert op.caminho_pasta == r"\\servidor\projetos\Cliente\OP123"
    assert resposta.headers["Location"].endswith(f"/op/{op.id}")
    assert OPSetor.query.filter_by(op_id=op.id, setor_id=setores["Acabamento"].id).first()
    assert Notificacao.query.filter_by(op_id=op.id, usuario="PCP", tipo_evento="op_criada").first()


def test_criacao_duplicada_de_op_em_sequencia_nao_cria_duas(client, login_as, setores):
    login_as("ATENDENTE")
    dados = {
        "nome": "OP Duplicada",
        "cliente": "Cliente Duplicado",
        "prazo": "2026-05-20",
        "setores": [str(setores["Acabamento"].id)],
    }

    primeira = client.post("/criar_op", data=dados)
    segunda = client.post("/criar_op", data=dados, follow_redirects=True)

    ops = OP.query.filter_by(nome="OP Duplicada").all()
    assert primeira.status_code == 302
    assert segunda.status_code == 200
    assert len(ops) == 1
    assert "Esta ação já foi processada." in segunda.get_data(as_text=True)


def test_edicao_de_op_altera_caminho_pasta(client, login_as, op_com_setor):
    op, setor = op_com_setor
    login_as("ATENDENTE")

    resposta = client.post(f"/editar_op/{op.id}", data={
        "nome": op.nome,
        "prazo": "",
        "caminho_pasta": r"\\servidor\projetos\Cliente\OP456",
        "setores": [str(setor.id)],
    })

    db.session.refresh(op)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith(f"/op/{op.id}")
    assert op.caminho_pasta == r"\\servidor\projetos\Cliente\OP456"


def test_edicao_de_op_altera_cliente(client, login_as, op_com_setor):
    op, setor = op_com_setor
    op.cliente = "Cliente Antigo"
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.post(f"/editar_op/{op.id}", data={
        "nome": op.nome,
        "cliente": "Cliente Atualizado",
        "prazo": "",
        "caminho_pasta": op.caminho_pasta or "",
        "setores": [str(setor.id)],
    })

    db.session.refresh(op)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith(f"/op/{op.id}")
    assert op.cliente == "Cliente Atualizado"


def test_detalhe_de_op_mostra_cliente(client, login_as, op_com_setor):
    op, _ = op_com_setor
    op.cliente = "Cliente Detalhe"
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Cliente: Cliente Detalhe" in html


def test_detalhe_de_op_mostra_cliente_nao_informado(client, login_as, op_com_setor):
    op, _ = op_com_setor
    op.cliente = None
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Cliente: Não informado" in html


def test_detalhe_de_op_mostra_botao_para_copiar_caminho_pasta(client, login_as, op_com_setor):
    op, _ = op_com_setor
    op.caminho_pasta = r"\\servidor\projetos\Cliente\OP789"
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Copiar pasta da OP" in html
    assert "Caminho copiado!" in html
    assert "file://" not in html
    assert r"\\servidor\projetos\Cliente\OP789" in html


def test_criacao_de_op_nao_envia_email_operacional_com_config_global_desligada(client, app, login_as, setores, monkeypatch, capsys):
    limpar_env_email(monkeypatch)
    limpar_config_email(app)
    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = False
    login_as("ATENDENTE")

    resposta = client.post("/criar_op", data={
        "nome": "OP Email Operacional",
        "prazo": "2026-05-20",
        "alta_prioridade": "on",
        "setores": [str(setores["Acabamento"].id)],
    })

    saida = capsys.readouterr().out
    op = OP.query.filter_by(nome="OP Email Operacional").first()
    assert resposta.status_code == 302
    assert op is not None
    notificacao = Notificacao.query.filter_by(op_id=op.id, usuario="PCP", tipo_evento="op_criada").first()
    assert notificacao is not None
    assert notificacao.email_enviado is False
    assert "[EMAIL OPERACIONAL][DEV]" not in saida


def test_falha_smtp_operacional_nao_quebra_criacao_de_op(client, app, login_as, setores, monkeypatch, caplog):
    import app as app_module

    services = app_module.notificacoes_module
    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def falhar_smtp(*args, **kwargs):
        raise RuntimeError("smtp indisponivel")

    monkeypatch.setattr(services, "enviar_email_smtp", falhar_smtp)
    caplog.set_level("ERROR")
    login_as("ATENDENTE")

    resposta = client.post("/criar_op", data={
        "nome": "OP SMTP Falho",
        "prazo": "2026-05-20",
        "setores": [str(setores["Acabamento"].id)],
    })

    op = OP.query.filter_by(nome="OP SMTP Falho").first()
    assert resposta.status_code == 302
    assert op is not None
    notificacao = Notificacao.query.filter_by(op_id=op.id, usuario="PCP", tipo_evento="op_criada").first()
    assert notificacao is not None
    assert notificacao.email_enviado is False
    assert "email_operacional_erro_smtp_ignorado evento=op_criada tipo=RuntimeError" in caplog.text


def test_email_operacional_nao_repete_notificacao_existente(app, capsys, monkeypatch):
    limpar_env_email(monkeypatch)
    limpar_config_email(app)
    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True

    import app as app_module

    services = app_module.notificacoes_module
    op = OP(
        nome="OP Email Sem Duplicar",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        prazo_final=date(2026, 5, 20),
    )
    db.session.add(op)
    db.session.flush()

    primeira = services.criar_notificacao(
        "PCP",
        services.mensagem_op("op_criada", op),
        link=services.link_op(op.id),
        op_id=op.id,
        tipo_evento="op_criada"
    )
    services.enviar_email_operacional(
        "op_criada",
        op=op,
        link=services.link_op(op.id),
        notificacoes=[primeira]
    )
    primeira_saida = capsys.readouterr().out

    repetida = services.criar_notificacao(
        "PCP",
        services.mensagem_op("op_criada", op),
        link=services.link_op(op.id),
        op_id=op.id,
        tipo_evento="op_criada"
    )
    services.enviar_email_operacional(
        "op_criada",
        op=op,
        link=services.link_op(op.id),
        notificacoes=[repetida]
    )
    segunda_saida = capsys.readouterr().out

    assert "[EMAIL OPERACIONAL][DEV]" in primeira_saida
    assert segunda_saida == ""


def test_notificacao_de_atraso_chama_servico_de_email(app, setores, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    setor = setores["Acabamento"]
    op = OP(
        nome="OP Com Tarefa Atrasada",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        prazo_final=hoje_brasilia() + timedelta(days=5),
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Tarefa atrasada para email",
        prazo=hoje_brasilia() - timedelta(days=1),
        validado=False,
    )
    db.session.add(tarefa)
    db.session.commit()

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas.append({
            "destinatarios": destinatarios,
            "assunto": assunto,
            "texto": texto,
            "html": html,
        })

        class Resultado:
            enviado = True
            erro = None

        return Resultado()

    monkeypatch.setattr(services, "smtp_configurado", lambda: True)
    monkeypatch.setattr(services, "enviar_email_smtp", enviar_email_fake)

    assert services.gerar_notificacoes_pendentes(forcar=True) is True

    assert chamadas
    assert "TAREFA ATRASADA" in chamadas[0]["assunto"]
    assert "setor@teste.com" in chamadas[0]["destinatarios"]
    assert "atendente@teste.com" in chamadas[0]["destinatarios"]
    assert "pcp@teste.com" in chamadas[0]["destinatarios"]


def test_destinatarios_nova_op_usam_tipo_pcp_mesmo_com_setor(app, setores):
    import app as app_module

    services = app_module.notificacoes_module
    pcp = User.query.filter_by(email="pcp@teste.com").first()
    pcp.setor_id = setores["PCP"].id
    db.session.commit()

    emails = services.destinatarios_email_operacional("op_criada")

    assert emails == ["pcp@teste.com"]


def test_destinatarios_de_setor_usam_setor_id_para_qualquer_tipo(app, setores):
    import app as app_module

    services = app_module.notificacoes_module
    pcp_setor = User(
        email="pcp.vinculado@teste.com",
        senha="123",
        tipo="PCP",
        setor_id=setores["PCP"].id,
        ativo=True
    )
    setor_pcp = User(
        email="setor.pcp@teste.com",
        senha="123",
        tipo="SETOR",
        setor_id=setores["PCP"].id,
        ativo=True
    )
    db.session.add_all([pcp_setor, setor_pcp])
    db.session.commit()

    emails = services.destinatarios_por_setor(setores["PCP"].id)

    assert emails == ["pcp.vinculado@teste.com", "setor.pcp@teste.com"]


def test_criacao_de_tarefa_notifica_setor(client, login_as, op_com_setor):
    op, setor = op_com_setor
    login_as("PCP")

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={"nome": "Imprimir material", "prazo": "2026-05-21"},
        headers={"Referer": f"/op/{op.id}"}
    )

    tarefa = Tarefa.query.filter_by(op_id=op.id, setor_id=setor.id).first()
    assert resposta.status_code == 302
    assert tarefa is not None
    assert tarefa.nome == "Imprimir material"
    assert tarefa.status == "PENDENTE"
    assert tarefa.criada_em is not None
    assert Notificacao.query.filter_by(
        usuario="SETOR",
        op_id=op.id,
        tarefa_id=tarefa.id,
        setor_id=setor.id,
        tipo_evento="tarefa_criada"
    ).first()


def test_criacao_duplicada_de_tarefa_em_sequencia_nao_cria_duas(client, login_as, op_com_setor):
    op, setor = op_com_setor
    login_as("PCP")
    dados = {"nome": "Tarefa Duplicada", "prazo": "2026-05-21"}

    primeira = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data=dados,
        headers={"Referer": f"/op/{op.id}"}
    )
    segunda = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data=dados,
        headers={"Referer": f"/op/{op.id}"},
        follow_redirects=True
    )

    tarefas = Tarefa.query.filter_by(op_id=op.id, setor_id=setor.id, nome="Tarefa Duplicada").all()
    assert primeira.status_code == 302
    assert segunda.status_code == 200
    assert len(tarefas) == 1
    assert "Esta ação já foi processada." in segunda.get_data(as_text=True)


def test_setor_inicia_tarefa_pendente(client, login_as, tarefa):
    inicio_anterior = datetime(2026, 5, 1, 8, 30)
    tarefa.iniciada_em = inicio_anterior
    db.session.commit()
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"
    assert tarefa.entregue is False
    assert tarefa.validado is False
    assert tarefa.iniciada_em == inicio_anterior
    assert Notificacao.query.filter_by(
        usuario="ATENDENTE",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_em_andamento"
    ).first()


def test_entrega_de_tarefa_notifica_atendente_e_pcp(client, login_as, tarefa):
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM VALIDAÇÃO"
    assert tarefa.entregue is True
    assert tarefa.validado is False
    assert tarefa.enviada_validacao_em is not None
    assert tarefa.entregue_em is not None
    assert Notificacao.query.filter_by(
        usuario="atendente@teste.com",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()
    assert Notificacao.query.filter_by(
        usuario="PCP",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()


def test_entrega_de_tarefa_salva_observacao_e_exibe_no_detalhe(client, login_as, tarefa):
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        data={"observacao_entrega": "Material entregue na bancada 2."},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.observacao_entrega == "Material entregue na bancada 2."

    login_as("ADMIN")
    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)
    assert "Observacao da entrega" in html
    assert "Material entregue na bancada 2." in html


def test_entrega_de_tarefa_sem_observacao_continua_funcionando(client, login_as, tarefa):
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        data={"observacao_entrega": ""},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM VALIDAÇÃO"
    assert tarefa.observacao_entrega is None


def test_entrega_de_tarefa_com_responsavel_notifica_validadores(client, login_as, tarefa, app, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas_email = []
    responsavel = User(
        email="responsavel.validacao@teste.com",
        senha="hash",
        tipo="SETOR",
        setor_id=tarefa.setor_id,
        ativo=True,
    )
    db.session.add(responsavel)
    db.session.flush()
    tarefa.responsaveis = [responsavel]
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    login_as("SETOR", email="responsavel.validacao@teste.com", setor_id=tarefa.setor_id)

    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas_email.append(destinatarios)

        class Resultado:
            enviado = True
            erro = None

        return Resultado()

    monkeypatch.setattr(services, "enviar_email_smtp", enviar_email_fake)

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    assert resposta.status_code == 302
    assert Notificacao.query.filter_by(
        usuario="atendente@teste.com",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()
    assert Notificacao.query.filter_by(
        usuario="PCP",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()
    assert not Notificacao.query.filter_by(
        usuario="responsavel.validacao@teste.com",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()
    assert chamadas_email == [["atendente@teste.com", "pcp@teste.com"]]


def test_validacao_de_tarefa_notifica_setor(client, login_as, tarefa):
    tarefa.status = "EM VALIDAÇÃO"
    tarefa.entregue = True
    db.session.commit()
    login_as("ADMIN")

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.entregue is True
    assert tarefa.validado is True
    assert tarefa.validada_em is not None
    assert tarefa.concluida_em is not None
    assert Notificacao.query.filter_by(
        usuario="SETOR",
        tarefa_id=tarefa.id,
        tipo_evento="entrega_validada"
    ).first()


def test_recusa_de_tarefa_reabre_entrega_e_notifica_setor(client, login_as, tarefa):
    tarefa.status = "EM VALIDAÇÃO"
    tarefa.entregue = True
    tarefa.validado = False
    db.session.commit()
    login_as("ADMIN")

    resposta = client.post(
        f"/recusar_tarefa/{tarefa.id}",
        data={"motivo_recusa": "Ajustar acabamento"},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "PENDENTE"
    assert tarefa.entregue is False
    assert tarefa.validado is False
    assert tarefa.recusada_em is not None
    assert tarefa.motivo_recusa == "Ajustar acabamento"
    notificacao_recusa = Notificacao.query.filter_by(
        usuario="SETOR",
        tarefa_id=tarefa.id,
        tipo_evento="entrega_recusada"
    ).first()
    assert notificacao_recusa
    assert "Motivo: Ajustar acabamento" in notificacao_recusa.mensagem


def test_recusa_de_tarefa_exige_motivo(client, login_as, tarefa):
    tarefa.status = "EM VALIDAÇÃO"
    tarefa.entregue = True
    tarefa.validado = False
    db.session.commit()
    login_as("ADMIN")

    resposta = client.post(
        f"/recusar_tarefa/{tarefa.id}",
        data={"motivo_recusa": ""},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 400
    assert tarefa.status == "EM VALIDAÇÃO"
    assert tarefa.entregue is True
    assert tarefa.validado is False


def test_fluxo_completo_status_tarefa(client, login_as, tarefa):
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"
    assert tarefa.entregue is False
    assert tarefa.validado is False
    assert tarefa.iniciada_em is not None

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM VALIDAÇÃO"
    assert tarefa.entregue is True
    assert tarefa.validado is False
    assert tarefa.enviada_validacao_em is not None
    assert tarefa.entregue_em is not None

    login_as("ADMIN")
    resposta = client.post(
        f"/recusar_tarefa/{tarefa.id}",
        data={"motivo_recusa": "Refazer acabamento"},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "PENDENTE"
    assert tarefa.entregue is False
    assert tarefa.validado is False
    assert tarefa.recusada_em is not None
    assert tarefa.motivo_recusa == "Refazer acabamento"

    login_as("SETOR", setor_id=tarefa.setor_id)
    client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM VALIDAÇÃO"

    login_as("SETOR", setor_id=tarefa.setor_id)
    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.entregue is True
    assert tarefa.validado is True
    assert tarefa.validada_em is not None
    assert tarefa.concluida_em is not None


def test_finalizacao_de_op_registra_data(client, login_as, tarefa):
    tarefa.status = "ENTREGUE"
    tarefa.entregue = True
    tarefa.validado = True
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.post(
        f"/finalizar_op/{tarefa.op_id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    op = db.session.get(OP, tarefa.op_id)
    assert resposta.status_code == 302
    assert op.status == "FINALIZADA"
    assert op.finalizada_em is not None


def test_arquivamento_de_op_registra_data(client, login_as, op_com_setor):
    op, _ = op_com_setor
    login_as("ATENDENTE")

    resposta = client.post(
        f"/arquivar_op/{op.id}",
        headers={"Referer": "/dashboard"}
    )

    db.session.refresh(op)
    assert resposta.status_code == 302
    assert op.status == "ARQUIVADA"
    assert op.arquivada_em is not None


def test_api_notificacoes_lista_notificacoes_do_usuario(client, login_as, notificacao):
    login_as("ATENDENTE")

    resposta = client.get("/api/notificacoes")
    dados = resposta.get_json()

    assert resposta.status_code == 200
    assert dados["total"] == 1
    assert dados["notificacoes"][0]["id"] == notificacao.id


def test_marcar_notificacao_individual_por_papel(client, login_as, notificacao):
    login_as("ATENDENTE")

    resposta = client.post(
        f"/ler_notificacao/{notificacao.id}",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )

    db.session.refresh(notificacao)
    assert resposta.status_code == 200
    assert notificacao.lida is True


def test_marcar_notificacao_individual_por_email(client, login_as, tarefa):
    notificacao = Notificacao(
        usuario="atendente@teste.com",
        mensagem="Notificacao por email",
        op_id=tarefa.op_id,
        tarefa_id=tarefa.id,
        setor_id=tarefa.setor_id,
        tipo_evento="tarefa_aguardando_validacao"
    )
    db.session.add(notificacao)
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.post(
        f"/ler_notificacao/{notificacao.id}",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )

    db.session.refresh(notificacao)
    assert resposta.status_code == 200
    assert notificacao.lida is True


def test_setor_marca_notificacao_individual_do_proprio_setor(client, login_as, tarefa):
    notificacao = Notificacao(
        usuario="SETOR",
        mensagem="Notificacao do setor",
        op_id=tarefa.op_id,
        tarefa_id=tarefa.id,
        setor_id=tarefa.setor_id,
        tipo_evento="tarefa_criada"
    )
    db.session.add(notificacao)
    db.session.commit()
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/ler_notificacao/{notificacao.id}",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )

    db.session.refresh(notificacao)
    assert resposta.status_code == 200
    assert notificacao.lida is True


def test_setor_nao_marca_notificacao_individual_de_outro_setor(client, login_as, tarefa, setores):
    notificacao = Notificacao(
        usuario="SETOR",
        mensagem="Notificacao de outro setor",
        op_id=tarefa.op_id,
        tarefa_id=tarefa.id,
        setor_id=setores["PCP"].id,
        tipo_evento="tarefa_criada"
    )
    db.session.add(notificacao)
    db.session.commit()
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(
        f"/ler_notificacao/{notificacao.id}",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )

    db.session.refresh(notificacao)
    assert resposta.status_code == 403
    assert notificacao.lida is False


def test_usuario_nao_marca_notificacao_individual_de_outro_email(client, login_as, tarefa):
    notificacao = Notificacao(
        usuario="pcp@teste.com",
        mensagem="Notificacao de outro email",
        op_id=tarefa.op_id,
        tarefa_id=tarefa.id,
        setor_id=tarefa.setor_id,
        tipo_evento="tarefa_aguardando_validacao"
    )
    db.session.add(notificacao)
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.post(
        f"/ler_notificacao/{notificacao.id}",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )

    db.session.refresh(notificacao)
    assert resposta.status_code == 403
    assert notificacao.lida is False


def test_marcar_todas_notificacoes_lidas_altera_apenas_usuario_logado(client, login_as, tarefa):
    notificacoes = [
        Notificacao(
            usuario="ATENDENTE",
            mensagem="Notificacao atendente 1",
            op_id=tarefa.op_id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="tarefa_aguardando_validacao"
        ),
        Notificacao(
            usuario="ATENDENTE",
            mensagem="Notificacao atendente 2",
            op_id=tarefa.op_id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="tarefa_aguardando_validacao"
        ),
        Notificacao(
            usuario="PCP",
            mensagem="Notificacao PCP",
            op_id=tarefa.op_id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="tarefa_aguardando_validacao"
        ),
    ]
    db.session.add_all(notificacoes)
    db.session.commit()

    login_as("ATENDENTE")

    resposta = client.post(
        "/notificacoes/marcar_todas_lidas",
        headers={"X-Requested-With": "XMLHttpRequest"}
    )
    dados = resposta.get_json()

    assert resposta.status_code == 200
    assert dados["total"] == 0
    assert dados["mensagem"] == "Todas as notificações foram marcadas como lidas."
    assert Notificacao.query.filter_by(usuario="ATENDENTE", lida=False).count() == 0
    assert Notificacao.query.filter_by(usuario="PCP", lida=False).count() == 1


def test_marcar_todas_notificacoes_lidas_zerando_contador_api(client, login_as, notificacao):
    login_as("ATENDENTE")

    resposta = client.post("/notificacoes/marcar_todas_lidas")

    assert resposta.status_code == 302
    db.session.refresh(notificacao)
    assert notificacao.lida is True

    resposta_api = client.get("/api/notificacoes")
    dados = resposta_api.get_json()
    assert dados["total"] == 0


def test_historico_notificacoes_exibe_feedback_apos_marcar_todas(client, login_as, notificacao):
    login_as("ATENDENTE")

    resposta = client.post(
        "/notificacoes/marcar_todas_lidas",
        headers={"Referer": "/notificacoes"},
        follow_redirects=True
    )
    html = resposta.get_data(as_text=True)

    db.session.refresh(notificacao)
    assert resposta.status_code == 200
    assert notificacao.lida is True
    assert "Todas as notificações foram marcadas como lidas." in html
    assert 'class="d-none"' in html
    assert "OK" not in html


def test_historico_notificacoes_oculta_botao_sem_nao_lidas(client, login_as, notificacao):
    notificacao.lida = True
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.get("/notificacoes")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Marcar todas como lidas" in html
    assert 'class="d-none"' in html


def test_marcar_todas_notificacoes_lidas_requer_login(client):
    resposta = client.post("/notificacoes/marcar_todas_lidas")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")


def test_teste_notificacao_bloqueia_production(client, login_as, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    login_as("ADMIN")

    resposta = client.get("/teste_notificacao")

    assert resposta.status_code == 404


def test_teste_notificacao_bloqueia_nao_admin(client, login_as, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    login_as("ATENDENTE")

    resposta = client.get("/teste_notificacao")

    assert resposta.status_code == 403


def test_seeds_de_teste_nao_rodam_em_production(app, monkeypatch):
    import app as app_module

    monkeypatch.setenv("APP_ENV", "production")

    assert app_module.config_module.ambiente_permite_seed_teste(app) is False
