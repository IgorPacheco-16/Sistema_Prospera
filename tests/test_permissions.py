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
