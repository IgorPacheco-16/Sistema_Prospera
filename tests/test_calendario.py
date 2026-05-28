from datetime import timedelta

from database.models import db, OP, OPSetor, Tarefa, User
from tempo import hoje_brasilia


def criar_op_calendario(nome_op, setor, nome_tarefa, **kwargs):
    op = OP(
        nome=nome_op,
        cliente=kwargs.pop("cliente", None),
        status=kwargs.pop("status_op", "EM ANDAMENTO"),
        atendente="atendente@teste.com",
        prazo_final=kwargs.pop("prazo_final", None),
        alta_prioridade=kwargs.pop("alta_prioridade", False),
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))

    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome=nome_tarefa,
        prazo=kwargs.pop("prazo", hoje_brasilia()),
        liberada=True,
        status=kwargs.pop("status_tarefa", "PENDENTE"),
        entregue=kwargs.pop("entregue", False),
        validado=kwargs.pop("validado", False),
        **kwargs,
    )
    db.session.add(tarefa)
    db.session.commit()
    return op, tarefa


def criar_usuario_calendario(email, setor, nome):
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


def test_calendario_renderiza_normalmente(client, login_as, setores):
    setor = setores["Acabamento"]
    _op, tarefa = criar_op_calendario(
        "OP Calendario Render",
        setor,
        "Tarefa calendario render",
        cliente="Cliente Render",
    )
    usuario = criar_usuario_calendario("ana.calendario@teste.com", setor, "Ana Calendario")
    tarefa.responsaveis = [usuario]
    db.session.commit()
    login_as("PCP")

    resposta = client.get("/calendario")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Calend&aacute;rio de Tarefas" in html
    assert "OP Calendario Render" in html
    assert "Cliente Render" in html
    assert "Ana Calendario" in html
    assert f"/op/{tarefa.op_id}?setor={setor.id}&amp;tarefa={tarefa.id}" in html


def test_calendario_filtra_por_setor(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    criar_op_calendario("OP Setor Visivel", acabamento, "Tarefa setor visivel")
    criar_op_calendario("OP Setor Oculto", pcp, "Tarefa setor oculto")
    login_as("ADMIN")

    resposta = client.get("/calendario", query_string={"setores": str(acabamento.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa setor visivel" in html
    assert "Tarefa setor oculto" not in html


def test_calendario_filtra_por_responsavel_unico(client, login_as, setores):
    setor = setores["Acabamento"]
    ana = criar_usuario_calendario("ana.unico.calendario@teste.com", setor, "Ana Unico")
    bia = criar_usuario_calendario("bia.unico.calendario@teste.com", setor, "Bia Unico")
    _op_ana, tarefa_ana = criar_op_calendario("OP Ana Unico", setor, "Tarefa Ana Unico")
    _op_bia, tarefa_bia = criar_op_calendario("OP Bia Unico", setor, "Tarefa Bia Unico")
    tarefa_ana.responsaveis = [ana]
    tarefa_bia.responsaveis = [bia]
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/calendario", query_string={"responsavel": str(ana.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa Ana Unico" in html
    assert "Tarefa Bia Unico" not in html


def test_calendario_filtra_por_multiplos_responsaveis(client, login_as, setores):
    setor = setores["Acabamento"]
    ana = criar_usuario_calendario("ana.multi.calendario@teste.com", setor, "Ana Multi")
    bia = criar_usuario_calendario("bia.multi.calendario@teste.com", setor, "Bia Multi")
    caio = criar_usuario_calendario("caio.multi.calendario@teste.com", setor, "Caio Multi")
    _op_ana, tarefa_ana = criar_op_calendario("OP Ana Multi", setor, "Tarefa Ana Multi")
    _op_bia, tarefa_bia = criar_op_calendario("OP Bia Multi", setor, "Tarefa Bia Multi")
    _op_caio, tarefa_caio = criar_op_calendario("OP Caio Multi", setor, "Tarefa Caio Multi")
    tarefa_ana.responsaveis = [ana]
    tarefa_bia.responsaveis = [bia]
    tarefa_caio.responsaveis = [caio]
    db.session.commit()
    login_as("PCP")

    resposta = client.get(
        "/calendario",
        query_string=[
            ("responsavel", str(ana.id)),
            ("responsavel", str(bia.id)),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa Ana Multi" in html
    assert "Tarefa Bia Multi" in html
    assert "Tarefa Caio Multi" not in html


def test_calendario_filtra_sem_responsavel(client, login_as, setores):
    setor = setores["Acabamento"]
    ana = criar_usuario_calendario("ana.sem.calendario@teste.com", setor, "Ana Sem")
    criar_op_calendario("OP Geral Calendario", setor, "Tarefa geral calendario")
    _op_ana, tarefa_ana = criar_op_calendario("OP Atribuida Calendario", setor, "Tarefa atribuida calendario")
    tarefa_ana.responsaveis = [ana]
    db.session.commit()
    login_as("ATENDENTE")

    resposta = client.get("/calendario", query_string={"responsavel": "sem_responsavel"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa geral calendario" in html
    assert "Tarefa atribuida calendario" not in html
    assert "Geral do setor" in html


def test_calendario_filtra_por_status(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_calendario(
        "OP Status Andamento",
        setor,
        "Tarefa status andamento",
        status_tarefa="EM ANDAMENTO",
    )
    criar_op_calendario(
        "OP Status Pendente",
        setor,
        "Tarefa status pendente",
        status_tarefa="PENDENTE",
    )
    login_as("ADMIN")

    resposta = client.get("/calendario", query_string={"status": "EM ANDAMENTO"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa status andamento" in html
    assert "Tarefa status pendente" not in html


def test_calendario_filtra_por_cliente(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_calendario(
        "OP Cliente Ouro",
        setor,
        "Tarefa cliente ouro",
        cliente="Cliente Ouro",
    )
    criar_op_calendario(
        "OP Cliente Prata",
        setor,
        "Tarefa cliente prata",
        cliente="Cliente Prata",
    )
    login_as("PCP")

    resposta = client.get("/calendario", query_string={"cliente": "Ouro"})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa cliente ouro" in html
    assert "Tarefa cliente prata" not in html


def test_calendario_lista_clientes_sem_duplicar_e_em_ordem(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_calendario("OP Zeta 1", setor, "Tarefa Zeta 1", cliente="Zeta")
    criar_op_calendario("OP Alfa", setor, "Tarefa Alfa", cliente="Alfa")
    criar_op_calendario("OP Zeta 2", setor, "Tarefa Zeta 2", cliente="Zeta")
    login_as("PCP")

    resposta = client.get("/calendario")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert html.count('<option value="Zeta">') == 1
    assert html.index('<option value="Alfa">') < html.index('<option value="Zeta">')


def test_calendario_setor_nao_ve_tarefas_de_outro_setor(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    criar_op_calendario("OP Setor Proprio", acabamento, "Tarefa setor proprio")
    criar_op_calendario("OP Outro Setor", pcp, "Tarefa outro setor")
    login_as("SETOR", setor_id=acabamento.id)

    resposta = client.get("/calendario", query_string={"setores": str(pcp.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa setor proprio" in html
    assert "Tarefa outro setor" not in html
    assert f'value="{acabamento.id}"' in html


def test_calendario_espectador_ignora_filtro_de_responsavel(client, login_as, setores):
    setor = setores["Acabamento"]
    ana = criar_usuario_calendario("ana.espectador.calendario@teste.com", setor, "Ana Espectador")
    _op_ana, tarefa_ana = criar_op_calendario("OP Espectador Ana", setor, "Tarefa espectador atribuida")
    criar_op_calendario("OP Espectador Geral", setor, "Tarefa espectador geral")
    tarefa_ana.responsaveis = [ana]
    db.session.commit()
    login_as("ESPECTADOR")

    resposta = client.get("/calendario", query_string={"responsavel": str(ana.id)})
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa espectador atribuida" in html
    assert "Tarefa espectador geral" in html
    assert 'data-calendario-list="responsaveis"' not in html


def test_calendario_tarefas_aparecem_nas_secoes_corretas(client, login_as, setores):
    setor = setores["Acabamento"]
    hoje = hoje_brasilia()
    criar_op_calendario("OP Atrasada Secao", setor, "Tarefa atrasada secao", prazo=hoje - timedelta(days=3))
    criar_op_calendario("OP Hoje Secao", setor, "Tarefa hoje secao", prazo=hoje)
    criar_op_calendario("OP Amanha Secao", setor, "Tarefa amanha secao", prazo=hoje + timedelta(days=1))
    criar_op_calendario("OP Sete Secao", setor, "Tarefa sete secao", prazo=hoje + timedelta(days=5))
    criar_op_calendario("OP Trinta Secao", setor, "Tarefa trinta secao", prazo=hoje + timedelta(days=20))
    criar_op_calendario("OP Sem Prazo Secao", setor, "Tarefa sem prazo secao", prazo=None)
    login_as("ADMIN")

    resposta = client.get("/calendario")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa atrasada secao" in html
    assert "Atrasada" in html
    assert "3 dia(s)" in html
    assert "Tarefa hoje secao" in html
    assert "Vence hoje" in html
    assert "Tarefa amanha secao" in html
    assert "Vence amanh" in html
    assert "Tarefa sete secao" in html
    assert "Em 5 dias" in html
    assert "Tarefa trinta secao" in html
    assert "Em 20 dias" in html
    assert "Tarefa sem prazo secao" in html
    assert "Sem prazo" in html


def test_calendario_filtros_invalidos_nao_quebram(client, login_as, setores):
    setor = setores["Acabamento"]
    criar_op_calendario("OP Filtros Invalidos", setor, "Tarefa filtros invalidos")
    login_as("ADMIN")

    resposta = client.get(
        "/calendario",
        query_string=[
            ("setores", "abc"),
            ("ops", "999999"),
            ("responsavel", "invalido"),
            ("status", "STATUS INEXISTENTE"),
            ("periodo", "inexistente"),
            ("data_inicio", "data-ruim"),
            ("data_fim", "2026-99-99"),
        ],
    )
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Tarefa filtros invalidos" in html
