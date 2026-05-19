from datetime import date, timedelta

from database.models import db, OP, OPSetor, Tarefa


def criar_tarefa_slide(nome_op, nome_tarefa, setor, prazo, status_op="EM ANDAMENTO"):
    op = OP(
        nome=nome_op,
        status=status_op,
        atendente="atendente@teste.com",
    )
    db.session.add(op)
    db.session.flush()

    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome=nome_tarefa,
        prazo=prazo,
        status="PENDENTE",
        liberada=True,
    )
    db.session.add(tarefa)
    db.session.commit()
    return op, tarefa


def nomes_itens(categoria):
    return {item["tarefa"] for item in categoria}


def test_slides_exige_login(client):
    resposta = client.get("/slides")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")


def test_slides_espectador_acessa(client, login_as):
    login_as("ESPECTADOR")

    resposta = client.get("/slides")

    assert resposta.status_code == 200
    assert "Painel de entregas" in resposta.get_data(as_text=True)


def test_slides_setor_nao_acessa(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/slides")

    assert resposta.status_code == 403


def test_api_slides_retorna_categorias(client, login_as, setores):
    criar_tarefa_slide(
        "OP API Slides",
        "Tarefa API Slides",
        setores["Acabamento"],
        date.today(),
    )
    login_as("ADMIN")

    resposta = client.get("/api/slides")
    dados = resposta.get_json()

    assert resposta.status_code == 200
    assert "resumo" in dados
    assert "slides" in dados
    assert set(dados["categorias"]) == {
        "atrasadas",
        "hoje",
        "amanha",
        "proximos_15_dias",
    }
    assert "Tarefa API Slides" in nomes_itens(dados["categorias"]["hoje"])


def test_api_slides_nao_exibe_arquivadas_ou_finalizadas(client, login_as, setores):
    hoje = date.today()
    criar_tarefa_slide(
        "OP Ativa Slides",
        "Tarefa ativa slides",
        setores["Acabamento"],
        hoje,
    )
    criar_tarefa_slide(
        "OP Arquivada Slides",
        "Tarefa arquivada slides",
        setores["Acabamento"],
        hoje,
        status_op="ARQUIVADA",
    )
    criar_tarefa_slide(
        "OP Finalizada Slides",
        "Tarefa finalizada slides",
        setores["Acabamento"],
        hoje,
        status_op="FINALIZADA",
    )
    login_as("PCP")

    dados = client.get("/api/slides").get_json()
    nomes = nomes_itens(dados["categorias"]["hoje"])

    assert "Tarefa ativa slides" in nomes
    assert "Tarefa arquivada slides" not in nomes
    assert "Tarefa finalizada slides" not in nomes


def test_api_slides_classifica_atrasada_hoje_amanha_e_15_dias(client, login_as, setores):
    hoje = date.today()
    criar_tarefa_slide("OP Atrasada", "Tarefa atrasada", setores["Acabamento"], hoje - timedelta(days=1))
    criar_tarefa_slide("OP Hoje", "Tarefa hoje", setores["Acabamento"], hoje)
    criar_tarefa_slide("OP Amanha", "Tarefa amanha", setores["Acabamento"], hoje + timedelta(days=1))
    criar_tarefa_slide("OP Quinze", "Tarefa 15 dias", setores["Acabamento"], hoje + timedelta(days=15))
    criar_tarefa_slide("OP Futura", "Tarefa futura", setores["Acabamento"], hoje + timedelta(days=16))
    login_as("ATENDENTE")

    dados = client.get("/api/slides").get_json()

    assert "Tarefa atrasada" in nomes_itens(dados["categorias"]["atrasadas"])
    assert "Tarefa hoje" in nomes_itens(dados["categorias"]["hoje"])
    assert "Tarefa amanha" in nomes_itens(dados["categorias"]["amanha"])
    assert "Tarefa 15 dias" in nomes_itens(dados["categorias"]["proximos_15_dias"])
    assert "Tarefa futura" not in nomes_itens(dados["categorias"]["proximos_15_dias"])

    assert dados["resumo"]["total_atrasadas"] == 1
    assert dados["resumo"]["vencem_hoje"] == 1
    assert dados["resumo"]["vencem_amanha"] == 1
    assert dados["resumo"]["proximas_2_semanas"] == 1
