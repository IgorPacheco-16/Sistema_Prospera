from datetime import date, datetime, timedelta

from database.models import db, Notificacao, OP, OPSetor, Tarefa


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
