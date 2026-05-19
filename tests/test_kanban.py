from datetime import date, timedelta

from database.models import db, OP, OPSetor, Tarefa


def criar_op_com_tarefa(nome_op, setor, nome_tarefa, status="EM ANDAMENTO", **kwargs):
    prazo_final = kwargs.pop("prazo_final", None)
    status_tarefa = kwargs.pop("status_tarefa", None)
    op = OP(
        nome=nome_op,
        status=status,
        atendente="atendente@teste.com",
        prazo_final=prazo_final,
        alta_prioridade=kwargs.pop("alta_prioridade", False),
    )
    db.session.add(op)
    db.session.flush()

    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome=nome_tarefa,
        liberada=True,
        **kwargs,
    )
    if status_tarefa:
        tarefa.status = status_tarefa
    db.session.add(tarefa)
    db.session.commit()

    return op, tarefa


def test_kanban_setor_ve_apenas_tarefas_do_proprio_setor(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]

    criar_op_com_tarefa("OP Acabamento", acabamento, "Tarefa do setor")
    criar_op_com_tarefa("OP PCP", pcp, "Tarefa de outro setor")

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get("/kanban")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa do setor" in html
    assert "Tarefa de outro setor" not in html
    assert "OP Acabamento" in html
    assert "OP PCP" not in html


def test_kanban_perfis_amplos_veem_todos_os_setores(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]

    criar_op_com_tarefa("OP Acabamento", acabamento, "Tarefa acabamento")
    criar_op_com_tarefa("OP PCP", pcp, "Tarefa pcp")

    for tipo in ["ATENDENTE", "PCP"]:
        login_as(tipo)
        resposta = client.get("/kanban")
        html = resposta.get_data(as_text=True)

        assert resposta.status_code == 200
        assert "Tarefa acabamento" in html
        assert "Tarefa pcp" in html


def test_kanban_oculta_ops_finalizadas_e_arquivadas(client, login_as, setores):
    setor = setores["Acabamento"]

    criar_op_com_tarefa("OP Ativa", setor, "Tarefa ativa")
    criar_op_com_tarefa("OP Finalizada", setor, "Tarefa finalizada", status="FINALIZADA")
    criar_op_com_tarefa("OP Arquivada", setor, "Tarefa arquivada", status="ARQUIVADA")

    login_as("PCP")
    resposta = client.get("/kanban")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa ativa" in html
    assert "Tarefa finalizada" not in html
    assert "Tarefa arquivada" not in html


def test_kanban_ordena_atrasadas_prazo_menor_e_sem_prazo_por_ultimo(client, login_as, setores):
    setor = setores["Acabamento"]
    hoje = date.today()

    criar_op_com_tarefa("OP Sem Prazo", setor, "Tarefa sem prazo", prazo=None)
    criar_op_com_tarefa("OP Prazo Futuro", setor, "Tarefa prazo futuro", prazo=hoje + timedelta(days=2))
    criar_op_com_tarefa("OP Muito Atrasada", setor, "Tarefa muito atrasada", prazo=hoje - timedelta(days=5))
    criar_op_com_tarefa("OP Atrasada", setor, "Tarefa atrasada", prazo=hoje - timedelta(days=1))

    login_as("ATENDENTE")
    resposta = client.get("/kanban")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.index("Tarefa muito atrasada") < html.index("Tarefa atrasada")
    assert html.index("Tarefa atrasada") < html.index("Tarefa prazo futuro")
    assert html.index("Tarefa prazo futuro") < html.index("Tarefa sem prazo")


def test_kanban_card_linka_para_op_com_deep_link(client, login_as, setores):
    setor = setores["Acabamento"]
    op, tarefa = criar_op_com_tarefa("OP Link", setor, "Tarefa com link")

    login_as("PCP")
    resposta = client.get("/kanban")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert f"/op/{op.id}?setor={setor.id}&amp;tarefa={tarefa.id}" in html


def test_kanban_combina_busca_status_setor_op_tipo_e_prazo(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    hoje = date.today()

    op_alvo, _ = criar_op_com_tarefa(
        "OP Cliente Ouro",
        acabamento,
        "Montar balcão especial",
        alta_prioridade=True,
        prazo_final=hoje - timedelta(days=2),
        prazo=hoje - timedelta(days=1),
        status_tarefa="EM ANDAMENTO",
    )
    criar_op_com_tarefa(
        "OP Cliente Ouro",
        pcp,
        "Montar balcão outro setor",
        alta_prioridade=True,
        prazo_final=hoje - timedelta(days=2),
        prazo=hoje - timedelta(days=1),
        status_tarefa="EM ANDAMENTO",
    )
    criar_op_com_tarefa(
        "OP Cliente Prata",
        acabamento,
        "Montar balcão sem prioridade",
        alta_prioridade=False,
        prazo_final=hoje - timedelta(days=2),
        prazo=hoje - timedelta(days=1),
        status_tarefa="EM ANDAMENTO",
    )
    criar_op_com_tarefa(
        "OP Cliente Futuro",
        acabamento,
        "Montar balcão futuro",
        alta_prioridade=True,
        prazo_final=hoje + timedelta(days=5),
        prazo=hoje - timedelta(days=1),
        status_tarefa="EM ANDAMENTO",
    )

    login_as("ATENDENTE")
    resposta = client.get(
        "/kanban",
        query_string=[
            ("busca", "balcão"),
            ("status", "EM ANDAMENTO"),
            ("setores", str(acabamento.id)),
            ("ops", str(op_alvo.id)),
            ("tipos_op", "alta_prioridade"),
            ("tipos_op", "op_atrasada"),
            ("prazos", "atrasadas"),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Montar balcão especial" in html
    assert "Montar balcão outro setor" not in html
    assert "Montar balcão sem prioridade" not in html
    assert "Montar balcão futuro" not in html


def test_kanban_setor_nao_consegue_filtrar_outro_setor(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]

    criar_op_com_tarefa("OP Acabamento", acabamento, "Tarefa visível")
    criar_op_com_tarefa("OP PCP", pcp, "Tarefa escondida")

    login_as("SETOR", setor_id=acabamento.id)
    resposta = client.get("/kanban", query_string={"setores": str(pcp.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa visível" in html
    assert "Tarefa escondida" not in html
    assert f'value="{acabamento.id}"' in html


def test_kanban_filtra_prazo_sem_prazo_e_vencem_hoje(client, login_as, setores):
    setor = setores["Acabamento"]
    hoje = date.today()

    criar_op_com_tarefa("OP Sem Prazo", setor, "Tarefa sem prazo", prazo=None)
    criar_op_com_tarefa("OP Hoje", setor, "Tarefa hoje", prazo=hoje)
    criar_op_com_tarefa("OP Futuro", setor, "Tarefa futuro", prazo=hoje + timedelta(days=10))

    login_as("PCP")
    resposta = client.get(
        "/kanban",
        query_string=[("prazos", "sem_prazo"), ("prazos", "hoje")],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa sem prazo" in html
    assert "Tarefa hoje" in html
    assert "Tarefa futuro" not in html
