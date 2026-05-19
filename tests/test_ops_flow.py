from datetime import date, datetime, timedelta

from database.models import db, Notificacao, OP, OPSetor, Tarefa, User


def test_dashboard_carrega_logado(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/dashboard")

    assert resposta.status_code == 200


def test_calendario_mostra_apenas_tarefas_pendentes_de_ops_em_andamento(client, login_as, setores):
    setor = setores["Acabamento"]
    prazo = date.today() + timedelta(days=1)

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
        "prazo": "2026-05-20",
        "setores": [str(setores["Acabamento"].id)],
    })

    op = OP.query.filter_by(nome="OP Nova").first()
    assert resposta.status_code == 302
    assert op is not None
    assert op.criada_em is not None
    assert resposta.headers["Location"].endswith(f"/op/{op.id}")
    assert OPSetor.query.filter_by(op_id=op.id, setor_id=setores["Acabamento"].id).first()
    assert Notificacao.query.filter_by(op_id=op.id, usuario="PCP", tipo_evento="op_criada").first()


def test_criacao_de_op_envia_email_operacional_com_smtp_ausente(client, login_as, setores, monkeypatch, capsys):
    for chave in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
        monkeypatch.delenv(chave, raising=False)
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
    assert "[EMAIL OPERACIONAL][DESTINATARIOS] op_criada | SMTP ausente -> pcp@teste.com" in saida
    assert "[EMAIL OPERACIONAL][DEV]" in saida
    assert "Nova OP criada" in saida
    assert "pcp@teste.com" in saida
    assert f"/op/{op.id}" in saida


def test_email_operacional_nao_repete_notificacao_existente(app, capsys, monkeypatch):
    for chave in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
        monkeypatch.delenv(chave, raising=False)

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
        usuario="ATENDENTE",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()
    assert Notificacao.query.filter_by(
        usuario="PCP",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_aguardando_validacao"
    ).first()


def test_validacao_de_tarefa_notifica_setor(client, login_as, tarefa):
    tarefa.status = "EM VALIDAÇÃO"
    tarefa.entregue = True
    db.session.commit()
    login_as("ATENDENTE")

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
    login_as("ATENDENTE")

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
    login_as("ATENDENTE")

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

    login_as("ATENDENTE")
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

    login_as("ATENDENTE")
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
