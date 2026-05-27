from datetime import date, datetime, timedelta

from database.models import db, OP, OPSetor, Tarefa, User
from metricas_responsaveis import metricas_usuario, ranking_metricas_responsaveis


def bloco_metricas_responsaveis(html):
    inicio = html.index("M&eacute;tricas por respons&aacute;vel")
    fim = html.index("Rankings operacionais")
    return html[inicio:fim]


def criar_usuario_metricas(email, setor, nome):
    usuario = User(
        email=email,
        nome=nome,
        tipo="SETOR",
        setor_id=setor.id,
        ativo=True,
    )
    db.session.add(usuario)
    db.session.flush()
    return usuario


def criar_op_metricas(nome, setor, criada_em):
    op = OP(
        nome=nome,
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        criada_em=criada_em,
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    return op


def criar_tarefa_metricas(op, setor, nome, status, criada_em, **kwargs):
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome=nome,
        status=status,
        criada_em=criada_em,
        liberada=True,
        entregue=kwargs.pop("entregue", False),
        validado=kwargs.pop("validado", False),
        **kwargs
    )
    db.session.add(tarefa)
    return tarefa


def test_dashboard_minhas_metricas_conta_apenas_tarefas_do_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    hoje = date(2026, 5, 18)
    agora = datetime(2026, 5, 18, 9, 0)
    responsavel = criar_usuario_metricas(
        "ana.dashboard.metricas@teste.com",
        acabamento,
        "Ana Dashboard",
    )
    op = criar_op_metricas("OP Dashboard Minhas Metricas", acabamento, agora)

    tarefa_responsavel = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa dashboard responsavel",
        "PENDENTE",
        agora,
        prazo=hoje - timedelta(days=1),
    )
    tarefa_responsavel.responsaveis = [responsavel]
    criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa dashboard geral",
        "PENDENTE",
        agora,
        prazo=hoje - timedelta(days=1),
    )
    db.session.commit()
    login_as("SETOR", email=responsavel.email, setor_id=acabamento.id)

    resposta = client.get("/dashboard")
    html = resposta.get_data(as_text=True)
    inicio = html.index("Minhas m&eacute;tricas")
    bloco = html[inicio:inicio + 1200]

    assert resposta.status_code == 200
    assert "<span>Pendentes</span>" in bloco
    assert "<strong>1</strong>" in bloco
    assert "<span>Atrasadas</span>" in bloco
    assert "Tarefa dashboard geral" not in bloco


def test_metricas_usuario_ignora_tarefa_geral_do_setor(app, setores):
    acabamento = setores["Acabamento"]
    hoje = date(2026, 5, 18)
    agora = datetime(2026, 5, 18, 9, 0)
    responsavel = criar_usuario_metricas(
        "ana.ignora.geral@teste.com",
        acabamento,
        "Ana Ignora Geral",
    )
    op = criar_op_metricas("OP Geral Nao Individual", acabamento, agora)
    tarefa_geral = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa geral nao individual",
        "PENDENTE",
        agora,
        prazo=hoje - timedelta(days=1),
    )
    db.session.commit()

    minhas_metricas = metricas_usuario([tarefa_geral], responsavel, hoje)
    ranking = ranking_metricas_responsaveis([tarefa_geral], hoje)

    assert minhas_metricas["pendentes"] == 0
    assert minhas_metricas["atrasadas"] == 0
    assert ranking["usuarios"] == []
    assert ranking["geral_setor"]["nome"] == "Geral do setor"
    assert ranking["geral_setor"]["pendentes"] == 1
    assert ranking["geral_setor"]["atrasadas"] == 1


def test_metricas_multiplos_responsaveis_conta_para_todos(app, setores):
    acabamento = setores["Acabamento"]
    hoje = date(2026, 5, 18)
    agora = datetime(2026, 5, 18, 9, 0)
    ana = criar_usuario_metricas("ana.multi@teste.com", acabamento, "Ana Multi")
    bia = criar_usuario_metricas("bia.multi@teste.com", acabamento, "Bia Multi")
    op = criar_op_metricas("OP Multi Responsaveis", acabamento, agora)
    tarefa = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa multi responsaveis",
        "ENTREGUE",
        agora,
        validado=True,
    )
    tarefa.responsaveis = [ana, bia]
    db.session.commit()

    ranking = ranking_metricas_responsaveis([tarefa], hoje)
    concluidas_por_nome = {
        linha["nome"]: linha["concluidas"]
        for linha in ranking["usuarios"]
    }

    assert concluidas_por_nome == {
        "Ana Multi": 1,
        "Bia Multi": 1,
    }


def test_metricas_responsaveis_respeita_filtro_por_setor(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    agora = datetime(2026, 5, 18, 9, 0)
    ana = criar_usuario_metricas(
        "ana.filtro.setor@teste.com",
        acabamento,
        "Ana Filtro Setor",
    )
    bia = criar_usuario_metricas(
        "bia.filtro.setor@teste.com",
        pcp,
        "Bia Filtro Setor",
    )
    op = criar_op_metricas("OP Filtro Responsaveis", acabamento, agora)
    db.session.add(OPSetor(op_id=op.id, setor_id=pcp.id))
    tarefa_acabamento = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa responsavel acabamento",
        "ENTREGUE",
        agora,
        validado=True,
    )
    tarefa_acabamento.responsaveis = [ana]
    tarefa_pcp = criar_tarefa_metricas(
        op,
        pcp,
        "Tarefa responsavel pcp",
        "ENTREGUE",
        agora,
        validado=True,
    )
    tarefa_pcp.responsaveis = [bia]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/metricas", query_string=[("setores", str(acabamento.id))])
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    bloco = bloco_metricas_responsaveis(html)
    assert "Ana Filtro Setor" in bloco
    assert "Bia Filtro Setor" not in bloco


def test_metricas_responsaveis_respeita_filtro_por_usuario(client, login_as, setores):
    acabamento = setores["Acabamento"]
    agora = datetime(2026, 5, 18, 9, 0)
    ana = criar_usuario_metricas("ana.filtro.usuario@teste.com", acabamento, "Ana Filtro Usuario")
    bia = criar_usuario_metricas("bia.filtro.usuario@teste.com", acabamento, "Bia Filtro Usuario")
    op = criar_op_metricas("OP Filtro Usuario", acabamento, agora)
    tarefa_ana = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa Ana Filtro Usuario",
        "ENTREGUE",
        agora,
        validado=True,
    )
    tarefa_ana.responsaveis = [ana]
    tarefa_bia = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa Bia Filtro Usuario",
        "ENTREGUE",
        agora,
        validado=True,
    )
    tarefa_bia.responsaveis = [bia]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/metricas", query_string=[("responsaveis", str(ana.id))])
    bloco = bloco_metricas_responsaveis(resposta.get_data(as_text=True))

    assert resposta.status_code == 200
    assert "Ana Filtro Usuario" in bloco
    assert "Bia Filtro Usuario" not in bloco
    assert '"data": [0, 0, 0, 1]' in resposta.get_data(as_text=True)


def test_metricas_responsaveis_calcula_atraso_taxa_e_recusa_por_usuario(app, setores):
    acabamento = setores["Acabamento"]
    hoje = date(2026, 5, 18)
    agora = datetime(2026, 5, 18, 9, 0)
    ana = criar_usuario_metricas("ana.taxa@teste.com", acabamento, "Ana Taxa")
    op = criar_op_metricas("OP Taxas Responsavel", acabamento, agora)
    atrasada = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa atrasada taxa",
        "PENDENTE",
        agora,
        prazo=hoje - timedelta(days=1),
    )
    atrasada.responsaveis = [ana]
    recusada = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa recusada taxa",
        "PENDENTE",
        agora,
        recusada_em=agora,
        motivo_recusa="Ajustar arquivo",
    )
    recusada.responsaveis = [ana]
    db.session.commit()

    linha = ranking_metricas_responsaveis(Tarefa.query.all(), hoje)["usuarios"][0]

    assert linha["nome"] == "Ana Taxa"
    assert linha["total_atribuidas"] == 2
    assert linha["atrasadas"] == 1
    assert linha["recusadas"] == 1
    assert linha["taxa_atraso"] == 50.0
    assert linha["taxa_recusa"] == 50.0


def test_metricas_responsaveis_protege_divisao_por_zero():
    resultado = ranking_metricas_responsaveis([], date(2026, 5, 18))

    assert resultado["usuarios"] == []
    assert resultado["geral_setor"] is None
    assert resultado["totais"]["total_atribuidas"] == 0
    assert resultado["totais"]["taxa_atraso"] == 0.0
    assert resultado["totais"]["taxa_recusa"] == 0.0


def test_metricas_renderiza_nova_area_e_mantem_metricas_antigas(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/metricas")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "M&eacute;tricas por respons&aacute;vel" in html
    assert "Ranking de produtividade" in html
    assert "Rankings operacionais" in html
    assert "Quem mais entrega" in html
    assert "Quem mais atrasa" in html
    assert "Quem mais tem recusas" in html
    assert "Quem tem mais tarefas em aberto" in html
    assert "Quem conclui mais r&aacute;pido" in html
    assert "Setores mais sobrecarregados" in html
    assert "Gargalos por setor" in html
    assert "Tarefas sem respons&aacute;vel" in html
    assert "Tarefas que mais demoraram" in html
    assert "OPs abertas h&aacute; mais tempo" in html
    assert "Tarefas por status" in html
    inicio_tabela = html.index("data-metricas-ranking-principal")
    fim_tabela = html.index("</table>", inicio_tabela)
    tabela = html[inicio_tabela:fim_tabela]
    assert "<th>Usu&aacute;rio</th>" in tabela
    assert "<th>Setor</th>" in tabela
    assert "<th>Total</th>" in tabela
    assert "<th>Entregues</th>" in tabela
    assert "<th>Recusadas</th>" in tabela
    assert "<th>Atrasadas</th>" in tabela
    assert "<th>Taxa de atraso</th>" in tabela
    assert "<th>Taxa de recusa</th>" in tabela
    assert "<th>Tempo m&eacute;dio de conclus&atilde;o</th>" in tabela


def test_ranking_responsaveis_ordena_por_concluidas_desc(app, setores):
    acabamento = setores["Acabamento"]
    hoje = date(2026, 5, 18)
    agora = datetime(2026, 5, 18, 9, 0)
    ana = criar_usuario_metricas("ana.ordem@teste.com", acabamento, "Ana Ordem")
    bia = criar_usuario_metricas("bia.ordem@teste.com", acabamento, "Bia Ordem")
    op = criar_op_metricas("OP Ranking Responsaveis", acabamento, agora)

    tarefa_ana = criar_tarefa_metricas(
        op,
        acabamento,
        "Tarefa Ana Ordem",
        "ENTREGUE",
        agora,
        validado=True,
    )
    tarefa_ana.responsaveis = [ana]
    for indice in range(2):
        tarefa_bia = criar_tarefa_metricas(
            op,
            acabamento,
            f"Tarefa Bia Ordem {indice}",
            "ENTREGUE",
            agora,
            validado=True,
        )
        tarefa_bia.responsaveis = [bia]
    db.session.commit()

    ranking = ranking_metricas_responsaveis(Tarefa.query.all(), hoje)["usuarios"]

    assert [linha["nome"] for linha in ranking[:2]] == ["Bia Ordem", "Ana Ordem"]
    assert [linha["concluidas"] for linha in ranking[:2]] == [2, 1]
