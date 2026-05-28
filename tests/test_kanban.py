from datetime import timedelta

from database.models import db, OP, OPSetor, Tarefa, User
from tempo import hoje_brasilia


def criar_op_com_tarefa(nome_op, setor, nome_tarefa, status="EM ANDAMENTO", **kwargs):
    prazo_final = kwargs.pop("prazo_final", None)
    status_tarefa = kwargs.pop("status_tarefa", None)
    op = OP(
        nome=nome_op,
        cliente=kwargs.pop("cliente", None),
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


def criar_usuario_kanban(email, setor, nome):
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
    hoje = hoje_brasilia()

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
    hoje = hoje_brasilia()

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


def test_kanban_filtra_por_cliente_com_filtros_existentes(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]

    criar_op_com_tarefa(
        "OP Cliente Alvo",
        acabamento,
        "Tarefa cliente alvo",
        cliente="Cliente Ouro",
        status_tarefa="EM ANDAMENTO",
    )
    criar_op_com_tarefa(
        "OP Cliente Errado",
        acabamento,
        "Tarefa cliente errado",
        cliente="Cliente Prata",
        status_tarefa="EM ANDAMENTO",
    )
    criar_op_com_tarefa(
        "OP Cliente Outro Setor",
        pcp,
        "Tarefa cliente outro setor",
        cliente="Cliente Ouro",
        status_tarefa="EM ANDAMENTO",
    )
    login_as("ADMIN")

    resposta = client.get(
        "/kanban",
        query_string=[
            ("cliente", "Ouro"),
            ("status", "EM ANDAMENTO"),
            ("setores", str(acabamento.id)),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa cliente alvo" in html
    assert "Tarefa cliente errado" not in html
    assert "Tarefa cliente outro setor" not in html
    assert 'data-kanban-filter-tab="cliente"' in html


def test_kanban_lista_clientes_sem_duplicar_e_em_ordem(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_com_tarefa("OP Zeta 1", setor, "Tarefa Zeta 1", cliente="Zeta")
    criar_op_com_tarefa("OP Alfa", setor, "Tarefa Alfa", cliente="Alfa")
    criar_op_com_tarefa("OP Zeta 2", setor, "Tarefa Zeta 2", cliente="Zeta")
    login_as("PCP")

    resposta = client.get("/kanban")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count('<option value="Zeta">') == 1
    assert html.index('<option value="Alfa">') < html.index('<option value="Zeta">')


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
    hoje = hoje_brasilia()

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


def test_kanban_admin_ve_filtro_por_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    criar_usuario_kanban("ana.kanban@teste.com", acabamento, "Ana Kanban")
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/kanban")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert 'data-kanban-filter-tab="responsavel"' in html
    assert "Usu&aacute;rio / respons&aacute;vel" in html
    assert "Ana Kanban" in html
    assert "Sem respons&aacute;vel" in html


def test_kanban_filtra_por_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.filtro.kanban@teste.com", acabamento, "Ana Filtro Kanban")
    bia = criar_usuario_kanban("bia.filtro.kanban@teste.com", acabamento, "Bia Filtro Kanban")
    _op_ana, tarefa_ana = criar_op_com_tarefa("OP Ana Kanban", acabamento, "Tarefa da Ana")
    _op_bia, tarefa_bia = criar_op_com_tarefa("OP Bia Kanban", acabamento, "Tarefa da Bia")
    tarefa_ana.responsaveis = [ana]
    tarefa_bia.responsaveis = [bia]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/kanban", query_string={"responsavel": str(ana.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa da Ana" in html
    assert "Tarefa da Bia" not in html


def test_kanban_filtra_por_multiplos_responsaveis(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.multi.filtro.kanban@teste.com", acabamento, "Ana Multi Filtro")
    bia = criar_usuario_kanban("bia.multi.filtro.kanban@teste.com", acabamento, "Bia Multi Filtro")
    caio = criar_usuario_kanban("caio.multi.filtro.kanban@teste.com", acabamento, "Caio Multi Filtro")
    _op_ana, tarefa_ana = criar_op_com_tarefa("OP Ana Multi Filtro", acabamento, "Tarefa filtro Ana")
    _op_bia, tarefa_bia = criar_op_com_tarefa("OP Bia Multi Filtro", acabamento, "Tarefa filtro Bia")
    _op_caio, tarefa_caio = criar_op_com_tarefa("OP Caio Multi Filtro", acabamento, "Tarefa filtro Caio")
    tarefa_ana.responsaveis = [ana]
    tarefa_bia.responsaveis = [bia]
    tarefa_caio.responsaveis = [caio]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get(
        "/kanban",
        query_string=[
            ("responsavel", str(ana.id)),
            ("responsavel", str(bia.id)),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa filtro Ana" in html
    assert "Tarefa filtro Bia" in html
    assert "Tarefa filtro Caio" not in html


def test_kanban_aceita_responsaveis_em_lista_separada_por_virgula(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.csv.kanban@teste.com", acabamento, "Ana CSV Kanban")
    bia = criar_usuario_kanban("bia.csv.kanban@teste.com", acabamento, "Bia CSV Kanban")
    _op_ana, tarefa_ana = criar_op_com_tarefa("OP Ana CSV", acabamento, "Tarefa CSV Ana")
    _op_bia, tarefa_bia = criar_op_com_tarefa("OP Bia CSV", acabamento, "Tarefa CSV Bia")
    tarefa_ana.responsaveis = [ana]
    tarefa_bia.responsaveis = [bia]
    db.session.commit()
    login_as("PCP")

    resposta = client.get("/kanban", query_string={"responsaveis": f"{ana.id},{bia.id}"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa CSV Ana" in html
    assert "Tarefa CSV Bia" in html


def test_kanban_tarefa_com_multiplos_responsaveis_aparece_para_cada_um(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.multi.kanban@teste.com", acabamento, "Ana Multi Kanban")
    bia = criar_usuario_kanban("bia.multi.kanban@teste.com", acabamento, "Bia Multi Kanban")
    _op, tarefa = criar_op_com_tarefa("OP Multi Kanban", acabamento, "Tarefa multi Kanban")
    tarefa.responsaveis = [ana, bia]
    db.session.commit()
    login_as("PCP")

    html_ana = client.get("/kanban", query_string={"responsavel": str(ana.id)}).get_data(as_text=True)
    html_bia = client.get("/kanban", query_string={"responsavel": str(bia.id)}).get_data(as_text=True)

    assert "Tarefa multi Kanban" in html_ana
    assert "Tarefa multi Kanban" in html_bia


def test_kanban_tarefa_com_multiplos_responsaveis_nao_duplica(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.sem.duplicar.kanban@teste.com", acabamento, "Ana Sem Duplicar")
    bia = criar_usuario_kanban("bia.sem.duplicar.kanban@teste.com", acabamento, "Bia Sem Duplicar")
    _op, tarefa = criar_op_com_tarefa("OP Sem Duplicar", acabamento, "Tarefa sem duplicar Kanban")
    tarefa.responsaveis = [ana, bia]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get(
        "/kanban",
        query_string=[
            ("responsavel", str(ana.id)),
            ("responsavel", str(bia.id)),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count("Tarefa sem duplicar Kanban") == 1


def test_kanban_filtra_tarefas_sem_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.geral.kanban@teste.com", acabamento, "Ana Geral Kanban")
    _op_geral, _tarefa_geral = criar_op_com_tarefa("OP Geral Kanban", acabamento, "Tarefa geral Kanban")
    _op_ana, tarefa_ana = criar_op_com_tarefa("OP Com Responsavel Kanban", acabamento, "Tarefa atribuida Kanban")
    tarefa_ana.responsaveis = [ana]
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.get("/kanban", query_string={"responsavel": "sem_responsavel"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa geral Kanban" in html
    assert "Tarefa atribuida Kanban" not in html


def test_kanban_todos_ignora_filtro_de_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.todos.kanban@teste.com", acabamento, "Ana Todos Kanban")
    _op_geral, _tarefa_geral = criar_op_com_tarefa("OP Todos Geral", acabamento, "Tarefa todos geral")
    _op_ana, tarefa_ana = criar_op_com_tarefa("OP Todos Ana", acabamento, "Tarefa todos atribuida")
    tarefa_ana.responsaveis = [ana]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/kanban", query_string={"responsavel": ""})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa todos geral" in html
    assert "Tarefa todos atribuida" in html


def test_kanban_filtro_responsavel_nao_vaza_outro_setor_para_setor(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    responsavel_pcp = criar_usuario_kanban("pcp.kanban@teste.com", pcp, "PCP Kanban")
    criar_op_com_tarefa("OP Acabamento Responsavel", acabamento, "Tarefa visivel responsavel")
    _op_pcp, tarefa_pcp = criar_op_com_tarefa("OP PCP Responsavel", pcp, "Tarefa escondida responsavel")
    tarefa_pcp.responsaveis = [responsavel_pcp]
    db.session.commit()
    login_as("SETOR", setor_id=acabamento.id)

    resposta = client.get("/kanban", query_string={"responsavel": str(responsavel_pcp.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa visivel responsavel" in html
    assert "Tarefa escondida responsavel" not in html
    assert "PCP Kanban" not in html


def test_kanban_filtro_responsavel_combina_com_filtros_existentes(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    ana = criar_usuario_kanban("ana.combo.kanban@teste.com", acabamento, "Ana Combo Kanban")
    _op_alvo, tarefa_alvo = criar_op_com_tarefa(
        "OP Combo Alvo",
        acabamento,
        "Tarefa combo alvo",
        status_tarefa="EM ANDAMENTO",
    )
    _op_outro_status, tarefa_outro_status = criar_op_com_tarefa(
        "OP Combo Outro Status",
        acabamento,
        "Tarefa combo outro status",
        status_tarefa="PENDENTE",
    )
    _op_outro_setor, tarefa_outro_setor = criar_op_com_tarefa(
        "OP Combo Outro Setor",
        pcp,
        "Tarefa combo outro setor",
        status_tarefa="EM ANDAMENTO",
    )
    tarefa_alvo.responsaveis = [ana]
    tarefa_outro_status.responsaveis = [ana]
    tarefa_outro_setor.responsaveis = [ana]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get(
        "/kanban",
        query_string=[
            ("responsavel", str(ana.id)),
            ("status", "EM ANDAMENTO"),
            ("setores", str(acabamento.id)),
            ("busca", "combo"),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa combo alvo" in html
    assert "Tarefa combo outro status" not in html
    assert "Tarefa combo outro setor" not in html


def test_kanban_espectador_nao_recebe_filtro_novo_de_responsavel(client, login_as, setores):
    acabamento = setores["Acabamento"]
    ana = criar_usuario_kanban("ana.espectador.kanban@teste.com", acabamento, "Ana Espectador Kanban")
    _op_ana, tarefa_ana = criar_op_com_tarefa("OP Espectador Ana", acabamento, "Tarefa espectador atribuida")
    criar_op_com_tarefa("OP Espectador Geral", acabamento, "Tarefa espectador geral")
    tarefa_ana.responsaveis = [ana]
    db.session.commit()
    login_as("ESPECTADOR")

    resposta = client.get("/kanban", query_string={"responsavel": str(ana.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert 'data-kanban-filter-tab="responsavel"' not in html
    assert "Tarefa espectador atribuida" in html
    assert "Tarefa espectador geral" in html
