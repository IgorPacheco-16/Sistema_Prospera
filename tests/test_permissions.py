from datetime import timedelta

from database.models import db, OP, OPSetor, Tarefa
from tempo import hoje_brasilia


def test_setor_nao_pode_criar_op(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/criar_op")

    assert resposta.status_code == 403
    assert b"Acesso negado" in resposta.data


def test_atendente_pode_acessar_criar_op(client, login_as):
    login_as("ATENDENTE")

    resposta = client.get("/criar_op")

    assert resposta.status_code == 200


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


def test_setor_nao_acessa_detalhe_op_sem_vinculo(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    op = OP(
        nome="OP Sem Vinculo Setor",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=pcp.id))
    db.session.commit()

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get(f"/op/{op.id}")

    assert resposta.status_code == 403


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

    login_as("SETOR", setor_id=pcp.id)
    resposta = client.get(f"/op/{op.id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa PCP" in html
    assert "Tarefa Acabamento" not in html
    assert f'action="/iniciar_tarefa/{tarefa_pcp.id}"' in html
    assert f'action="/iniciar_tarefa/{tarefa_acabamento.id}"' not in html


def test_dashboard_setor_lista_apenas_ops_vinculadas(client, login_as, setores):
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
    db.session.add_all([op_acabamento, op_pcp])
    db.session.flush()
    db.session.add_all([
        OPSetor(op_id=op_acabamento.id, setor_id=acabamento.id),
        OPSetor(op_id=op_pcp.id, setor_id=pcp.id),
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
    assert "OP Dashboard PCP" not in html
    assert "Arquivar" not in html
    assert "Arquivadas" not in html


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
