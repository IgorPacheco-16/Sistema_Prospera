from datetime import timedelta

import pytest

from database.models import db, HistoricoOP, OP, OPSetor, Setor, Tarefa, TarefaResponsavel, User
from tempo import hoje_brasilia


def criar_tarefa_para_setor(setor, status="PENDENTE", entregue=False, validado=False):
    op = OP(
        nome=f"OP Permissao {setor.nome}",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome=f"Tarefa {setor.nome}",
        status=status,
        entregue=entregue,
        validado=validado,
        liberada=True
    )
    db.session.add(tarefa)
    db.session.commit()

    return op, tarefa


def obter_ou_criar_setor(nome):
    setor = Setor.query.filter_by(nome=nome).first()
    if setor:
        return setor

    setor = Setor(nome=nome)
    db.session.add(setor)
    db.session.commit()
    return setor


def executar_fluxo_operacional(client, tarefa, login_as, tipo):
    login_as(tipo)

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.entregue is True
    assert tarefa.validado is False

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )
    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.validado is True


def test_setor_nao_pode_criar_op(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/criar_op")

    assert resposta.status_code == 403
    assert b"Acesso negado" in resposta.data


def test_setor_nao_pode_postar_criar_op(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.post("/criar_op", data={
        "nome": "OP Sem Permissao",
        "prazo": "2026-05-20",
        "setores": [str(setores["Acabamento"].id)],
    })

    assert resposta.status_code == 403
    assert OP.query.filter_by(nome="OP Sem Permissao").first() is None


def test_atendente_pode_acessar_criar_op(client, login_as):
    login_as("ATENDENTE")

    resposta = client.get("/criar_op")

    assert resposta.status_code == 200


def test_criar_tarefa_post_requer_login(client, op_com_setor):
    op, setor = op_com_setor

    resposta = client.post(
        f"/criar_tarefa/{op.id}/{setor.id}",
        data={"nome": "Tarefa Sem Login", "prazo": "2026-05-21"},
    )

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")
    assert Tarefa.query.filter_by(nome="Tarefa Sem Login").first() is None


def test_pcp_nao_pode_editar_op(client, login_as, op_com_setor):
    op, _setor = op_com_setor
    login_as("PCP")

    resposta = client.get(f"/editar_op/{op.id}")

    assert resposta.status_code == 403


def test_setor_so_entrega_tarefa_do_proprio_setor(client, login_as, tarefa, setores):
    login_as("SETOR", setor_id=setores["PCP"].id)

    resposta = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    assert resposta.status_code == 403
    assert b"Setor incorreto" in resposta.data


def test_setor_nao_pode_iniciar_tarefa_de_outro_setor(client, login_as, tarefa, setores):
    login_as("SETOR", setor_id=setores["PCP"].id)

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    assert resposta.status_code == 403
    assert b"Setor incorreto" in resposta.data


def test_setor_inicia_e_entrega_apenas_tarefa_do_proprio_setor(
    client,
    login_as,
    setores,
):
    _op, tarefa = criar_tarefa_para_setor(setores["Acabamento"])
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    inicio = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    entrega = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    db.session.refresh(tarefa)

    assert inicio.status_code == 302
    assert entrega.status_code == 302
    assert tarefa.entregue is True
    assert tarefa.validado is False


def test_setor_acessa_detalhe_op_ativa_sem_vinculo(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    op = OP(
        nome="OP Panorama Sem Vinculo",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=pcp.id))
    db.session.add(Tarefa(
        op_id=op.id,
        setor_id=pcp.id,
        nome="Tarefa visivel de outro setor",
        status="PENDENTE",
        liberada=True
    ))
    db.session.commit()

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa visivel de outro setor" in html
    assert "/iniciar_tarefa/" not in html
    assert "/validar_tarefa/" not in html


def test_detalhe_op_setor_ve_acoes_apenas_do_proprio_setor(client, login_as, op_com_setor, setores):
    op, acabamento = op_com_setor
    pcp = setores["PCP"]
    db.session.add(OPSetor(op_id=op.id, setor_id=pcp.id))
    tarefa_acabamento = Tarefa(
        op_id=op.id,
        setor_id=acabamento.id,
        nome="Tarefa Acabamento",
        status="PENDENTE",
        liberada=True
    )
    tarefa_pcp = Tarefa(
        op_id=op.id,
        setor_id=pcp.id,
        nome="Tarefa PCP",
        status="PENDENTE",
        liberada=True
    )
    db.session.add_all([tarefa_acabamento, tarefa_pcp])
    db.session.commit()

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa PCP" in html
    assert "Tarefa Acabamento" in html
    assert f'action="/iniciar_tarefa/{tarefa_acabamento.id}"' in html
    assert f'action="/iniciar_tarefa/{tarefa_pcp.id}"' not in html


def test_setor_criacao_ve_e_aciona_tarefa_mesmo_sem_ser_responsavel(client, login_as):
    criacao = Setor(nome="Criacao")
    db.session.add(criacao)
    db.session.flush()
    usuario_criacao = User(
        email="criacao@teste.com",
        nome="Usuario Criacao",
        tipo="SETOR",
        setor_id=criacao.id,
        ativo=True,
    )
    outro_usuario_criacao = User(
        email="outro.criacao@teste.com",
        nome="Outro Criacao",
        tipo="SETOR",
        setor_id=criacao.id,
        ativo=True,
    )
    op = OP(
        nome="OP Criacao Vinculada",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
    )
    db.session.add_all([usuario_criacao, outro_usuario_criacao, op])
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=criacao.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=criacao.id,
        nome="Tarefa Criacao Geral",
        status="PENDENTE",
        liberada=True,
    )
    tarefa.responsaveis = [outro_usuario_criacao]
    db.session.add(tarefa)
    db.session.commit()

    login_as("SETOR", email=usuario_criacao.email, setor_id=criacao.id)
    dashboard = client.get("/dashboard").get_data(as_text=True)
    detalhe = client.get(f"/op/{op.id}").get_data(as_text=True)
    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{op.id}"}
    )

    db.session.refresh(tarefa)
    assert "OP Criacao Vinculada" in dashboard
    assert "Tarefa Criacao Geral" in detalhe
    assert f'action="/iniciar_tarefa/{tarefa.id}"' in detalhe
    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"


def test_dashboard_setor_lista_ops_ativas_sem_limitar_por_vinculo(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    op_acabamento = OP(
        nome="OP Dashboard Acabamento",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    op_pcp = OP(
        nome="OP Dashboard PCP",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    op_finalizada = OP(
        nome="OP Dashboard Finalizada",
        status="FINALIZADA",
        atendente="atendente@teste.com"
    )
    op_arquivada = OP(
        nome="OP Dashboard Arquivada",
        status="ARQUIVADA",
        atendente="atendente@teste.com"
    )
    db.session.add_all([op_acabamento, op_pcp, op_finalizada, op_arquivada])
    db.session.flush()
    db.session.add_all([
        OPSetor(op_id=op_acabamento.id, setor_id=acabamento.id),
        OPSetor(op_id=op_pcp.id, setor_id=pcp.id),
        OPSetor(op_id=op_finalizada.id, setor_id=acabamento.id),
        OPSetor(op_id=op_arquivada.id, setor_id=acabamento.id),
        Tarefa(
            op_id=op_acabamento.id,
            setor_id=acabamento.id,
            nome="Tarefa dashboard visivel",
            status="PENDENTE",
            liberada=True
        ),
        Tarefa(
            op_id=op_pcp.id,
            setor_id=pcp.id,
            nome="Tarefa dashboard escondida",
            status="PENDENTE",
            liberada=True
        ),
    ])
    db.session.commit()

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get("/dashboard")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Dashboard Acabamento" in html
    assert "OP Dashboard PCP" in html
    assert "OP Dashboard Finalizada" not in html
    assert "OP Dashboard Arquivada" not in html
    assert "Arquivar" not in html
    assert "Arquivadas" not in html

    finalizadas = client.get("/dashboard?status=FINALIZADA").get_data(as_text=True)
    assert "OP Dashboard Finalizada" not in finalizadas


def test_setor_nao_acessa_arquivadas(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/arquivadas")

    assert resposta.status_code == 403


def test_calendario_setor_ve_apenas_tarefas_do_proprio_setor(client, login_as, op_com_setor, setores):
    op, acabamento = op_com_setor
    pcp = setores["PCP"]
    op.nome = "OP Calendario Acabamento"
    op_pcp = OP(
        nome="OP Calendario PCP",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    db.session.add(op_pcp)
    db.session.flush()
    db.session.add(OPSetor(op_id=op_pcp.id, setor_id=pcp.id))
    db.session.add_all([
        Tarefa(
            op_id=op.id,
            setor_id=acabamento.id,
            nome="Tarefa calendario acabamento",
            prazo=hoje_brasilia() + timedelta(days=1),
            status="PENDENTE",
            liberada=True
        ),
        Tarefa(
            op_id=op_pcp.id,
            setor_id=pcp.id,
            nome="Tarefa calendario pcp",
            prazo=hoje_brasilia() + timedelta(days=1),
            status="PENDENTE",
            liberada=True
        ),
    ])
    db.session.commit()

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get("/calendario")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "OP Calendario Acabamento" in html
    assert "OP Calendario PCP" not in html


def test_pcp_ve_e_movimenta_tarefa_do_setor_pcp(client, login_as, setores):
    op, tarefa = criar_tarefa_para_setor(setores["PCP"])

    login_as("PCP")
    html = client.get(f"/op/{op.id}").get_data(as_text=True)

    assert f'action="/iniciar_tarefa/{tarefa.id}"' in html

    executar_fluxo_operacional(client, tarefa, login_as, "PCP")


@pytest.mark.parametrize("nome_setor", ["Terceirização", "Marcenaria"])
def test_pcp_inicia_e_envia_para_validacao_setores_autorizados(
    client,
    login_as,
    nome_setor,
):
    setor = obter_ou_criar_setor(nome_setor)
    op, tarefa = criar_tarefa_para_setor(setor)
    login_as("PCP")

    detalhe = client.get(f"/op/{op.id}").get_data(as_text=True)
    inicio = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{op.id}"},
    )
    db.session.refresh(tarefa)

    assert f'action="/iniciar_tarefa/{tarefa.id}"' in detalhe
    assert inicio.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"

    entrega = client.post(
        f"/entregar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{op.id}"},
    )
    db.session.refresh(tarefa)

    assert entrega.status_code == 302
    assert tarefa.entregue is True
    assert tarefa.validado is False


@pytest.mark.parametrize(
    "nome_setor",
    ["Criação", "Projetos", "Impressão", "Acabamento", "Instalação"],
)
def test_pcp_nao_opera_demais_setores(client, login_as, nome_setor):
    setor = obter_ou_criar_setor(nome_setor)
    op, tarefa = criar_tarefa_para_setor(setor)
    login_as("PCP")

    detalhe = client.get(f"/op/{op.id}").get_data(as_text=True)
    inicio = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{op.id}"},
    )
    db.session.refresh(tarefa)

    assert f'action="/iniciar_tarefa/{tarefa.id}"' not in detalhe
    assert inicio.status_code == 403
    assert tarefa.status == "PENDENTE"


def test_atendente_ve_e_movimenta_tarefa_do_setor_atendimento(client, login_as, setores):
    op, tarefa = criar_tarefa_para_setor(setores["Atendimento"])

    login_as("ATENDENTE")
    html = client.get(f"/op/{op.id}").get_data(as_text=True)

    assert f'action="/iniciar_tarefa/{tarefa.id}"' in html

    executar_fluxo_operacional(client, tarefa, login_as, "ATENDENTE")


def test_pcp_nao_movimenta_tarefa_de_outro_setor(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(setores["Acabamento"])
    login_as("PCP")

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 403
    assert tarefa.status == "PENDENTE"


def test_pcp_valida_tarefa_de_outro_setor_sem_iniciar(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÇÃO",
        entregue=True,
        validado=False,
    )
    login_as("PCP")

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.validado is True


def test_setor_nao_valida_tarefa_do_proprio_setor(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 403
    assert tarefa.validado is False


def test_atendente_valida_tarefa_de_outro_setor(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÇÃO",
        entregue=True,
        validado=False,
    )
    login_as("ATENDENTE")

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.validado is True


@pytest.mark.parametrize("tipo", ["ADMIN", "ATENDENTE", "PCP"])
def test_perfis_autorizados_validam_tarefa_entregue(client, login_as, setores, tipo):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    login_as(tipo)

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.validado is True


def test_atendente_valida_tarefa_sem_ser_criador_ou_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    _op, tarefa = criar_tarefa_para_setor(
        acabamento,
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    criador = User(
        email="criador.validacao@teste.com",
        nome="Criador Validacao",
        tipo="PCP",
        ativo=True,
    )
    responsavel = User(
        email="responsavel.validacao.permissao@teste.com",
        nome="Responsavel Validacao",
        tipo="SETOR",
        setor_id=acabamento.id,
        ativo=True,
    )
    db.session.add_all([criador, responsavel])
    db.session.flush()
    tarefa.criado_por_id = criador.id
    tarefa.responsaveis = [responsavel]
    db.session.commit()

    login_as("ATENDENTE")
    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "ENTREGUE"
    assert tarefa.validado is True


@pytest.mark.parametrize("tipo,setor_id_nome", [
    ("SETOR", "Acabamento"),
    ("ESPECTADOR", None),
])
def test_perfis_bloqueados_nao_validam_tarefa_por_post_direto(
    client,
    login_as,
    setores,
    tipo,
    setor_id_nome,
):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    setor_id = setores[setor_id_nome].id if setor_id_nome else None
    login_as(tipo, setor_id=setor_id)

    resposta = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 403
    assert tarefa.validado is False


@pytest.mark.parametrize("tipo", ["ADMIN", "ATENDENTE", "PCP"])
def test_perfis_autorizados_recusam_tarefa_entregue(client, login_as, setores, tipo):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    login_as(tipo)

    resposta = client.post(
        f"/recusar_tarefa/{tarefa.id}",
        data={"motivo_recusa": "Ajustar entrega"},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 302
    assert tarefa.status == "PENDENTE"
    assert tarefa.entregue is False
    assert tarefa.validado is False
    assert tarefa.motivo_recusa == "Ajustar entrega"


@pytest.mark.parametrize("tipo,setor_id_nome", [
    ("SETOR", "Acabamento"),
    ("ESPECTADOR", None),
])
def test_perfis_bloqueados_nao_recusam_tarefa_por_post_direto(
    client,
    login_as,
    setores,
    tipo,
    setor_id_nome,
):
    _op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    setor_id = setores[setor_id_nome].id if setor_id_nome else None
    login_as(tipo, setor_id=setor_id)

    resposta = client.post(
        f"/recusar_tarefa/{tarefa.id}",
        data={"motivo_recusa": "Tentativa indevida"},
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 403
    assert tarefa.entregue is True
    assert tarefa.validado is False
    assert tarefa.motivo_recusa is None


@pytest.mark.parametrize("tipo,setor_id_nome,pode_ver", [
    ("ADMIN", None, True),
    ("ATENDENTE", None, True),
    ("PCP", None, True),
    ("SETOR", "Acabamento", False),
    ("ESPECTADOR", None, False),
])
def test_botoes_validar_e_recusar_seguem_permissao_de_validacao(
    client,
    login_as,
    setores,
    tipo,
    setor_id_nome,
    pode_ver,
):
    op, tarefa = criar_tarefa_para_setor(
        setores["Acabamento"],
        status="EM VALIDAÃ‡ÃƒO",
        entregue=True,
        validado=False,
    )
    setor_id = setores[setor_id_nome].id if setor_id_nome else None
    login_as(tipo, setor_id=setor_id)

    html = client.get(f"/op/{op.id}").get_data(as_text=True)

    assert (f'action="/validar_tarefa/{tarefa.id}"' in html) is pode_ver
    assert (f'action="/recusar_tarefa/{tarefa.id}"' in html) is pode_ver


def test_atendente_nao_movimenta_tarefa_de_outro_setor(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(setores["Acabamento"])
    login_as("ATENDENTE")

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 403
    assert tarefa.status == "PENDENTE"


def test_espectador_nao_movimenta_tarefa(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(setores["Atendimento"])
    login_as("ESPECTADOR")

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"}
    )

    db.session.refresh(tarefa)
    assert resposta.status_code == 403
    assert tarefa.status == "PENDENTE"


@pytest.mark.parametrize(
    "tipo,setor_nome,pode_ver",
    [
        ("ADMIN", None, True),
        ("ATENDENTE", None, True),
        ("PCP", None, True),
        ("SETOR", "Acabamento", False),
        ("ESPECTADOR", None, False),
    ],
)
def test_historico_completo_da_op_segue_perfis_autorizados(
    client,
    login_as,
    setores,
    tipo,
    setor_nome,
    pode_ver,
):
    op, _tarefa = criar_tarefa_para_setor(setores["Acabamento"])
    db.session.add(HistoricoOP(
        op_id=op.id,
        acao="Evento confidencial de auditoria",
        usuario="autor.auditoria@teste.com",
        descricao="Prazo e setores alterados para teste de permissao.",
    ))
    db.session.commit()
    setor_id = setores[setor_nome].id if setor_nome else None
    login_as(tipo, setor_id=setor_id)

    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert ("historicoOPModal" in html) is pode_ver
    assert ("Evento confidencial de auditoria" in html) is pode_ver
    assert ("autor.auditoria@teste.com" in html) is pode_ver


def test_admin_movimenta_tarefa_de_qualquer_setor(client, login_as, setores):
    _op, tarefa = criar_tarefa_para_setor(setores["Acabamento"])

    executar_fluxo_operacional(client, tarefa, login_as, "ADMIN")


@pytest.mark.parametrize("status_op", ["FINALIZADA", "ARQUIVADA"])
def test_pcp_nao_opera_setores_autorizados_em_op_encerrada(
    client,
    login_as,
    status_op,
):
    setor = obter_ou_criar_setor("Marcenaria")
    op = OP(
        nome=f"OP PCP bloqueada {status_op}",
        status=status_op,
        atendente="atendente@teste.com",
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa_pendente = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Marcenaria pendente bloqueada",
        status="PENDENTE",
        liberada=True,
    )
    tarefa_em_andamento = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Marcenaria em andamento bloqueada",
        status="EM ANDAMENTO",
        liberada=True,
    )
    db.session.add_all([tarefa_pendente, tarefa_em_andamento])
    db.session.commit()
    login_as("PCP")

    inicio = client.post(f"/iniciar_tarefa/{tarefa_pendente.id}")
    entrega = client.post(f"/entregar_tarefa/{tarefa_em_andamento.id}")
    db.session.refresh(tarefa_pendente)
    db.session.refresh(tarefa_em_andamento)

    assert inicio.status_code == 400
    assert entrega.status_code == 400
    assert tarefa_pendente.status == "PENDENTE"
    assert tarefa_em_andamento.status == "EM ANDAMENTO"
    assert tarefa_em_andamento.entregue is False


@pytest.mark.parametrize("status_op", ["FINALIZADA", "ARQUIVADA"])
def test_op_finalizada_ou_arquivada_bloqueia_posts_operacionais(
    client,
    login_as,
    setores,
    status_op,
):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    op = OP(
        nome=f"OP Bloqueada {status_op}",
        status=status_op,
        atendente="atendente@teste.com",
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=acabamento.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=acabamento.id,
        nome="Tarefa bloqueada",
        status="EM VALIDAÇÃO",
        entregue=True,
        validado=False,
        liberada=True,
    )
    responsavel = User(
        email=f"bloqueado.{status_op.lower()}@teste.com",
        nome="Responsavel Bloqueado",
        tipo="SETOR",
        setor_id=acabamento.id,
        ativo=True,
    )
    db.session.add_all([tarefa, responsavel])
    db.session.commit()

    login_as("ADMIN")
    operacoes = [
        client.post(
            f"/criar_tarefa/{op.id}/{acabamento.id}",
            data={"nome": "Nova bloqueada", "prazo": ""},
            headers={"Referer": f"/op/{op.id}"},
        ),
        client.post(
            f"/editar_tarefa/{tarefa.id}",
            data={"nome": "Editada bloqueada", "prazo": ""},
            headers={"Referer": f"/op/{op.id}"},
        ),
        client.post(f"/excluir_tarefa/{tarefa.id}", headers={"Referer": f"/op/{op.id}"}),
        client.post(f"/iniciar_tarefa/{tarefa.id}", headers={"Referer": f"/op/{op.id}"}),
        client.post(f"/entregar_tarefa/{tarefa.id}", headers={"Referer": f"/op/{op.id}"}),
        client.post(f"/validar_tarefa/{tarefa.id}", headers={"Referer": f"/op/{op.id}"}),
        client.post(
            f"/recusar_tarefa/{tarefa.id}",
            data={"motivo_recusa": "Bloqueado"},
            headers={"Referer": f"/op/{op.id}"},
        ),
        client.post(
            f"/tarefas/{tarefa.id}/espera/solicitar",
            data={"motivo": "Bloqueado"},
            headers={"Referer": f"/op/{op.id}"},
        ),
        client.post(
            f"/tarefas/{tarefa.id}/responsaveis",
            data={"tipo": "INCLUSAO", "usuario_ids": [str(responsavel.id)]},
            headers={"Referer": f"/op/{op.id}"},
        ),
        client.post(
            f"/op/{op.id}/setores",
            data={"setores": [str(acabamento.id), str(pcp.id)]},
            headers={"Referer": f"/op/{op.id}"},
        ),
    ]

    assert all(resposta.status_code == 400 for resposta in operacoes)
    assert Tarefa.query.filter_by(op_id=op.id).count() == 1
    db.session.refresh(tarefa)
    assert tarefa.nome == "Tarefa bloqueada"
    assert tarefa.validado is False
    assert tarefa.motivo_recusa is None
    assert TarefaResponsavel.query.filter_by(tarefa_id=tarefa.id).count() == 0
    assert OPSetor.query.filter_by(op_id=op.id, setor_id=pcp.id).first() is None
