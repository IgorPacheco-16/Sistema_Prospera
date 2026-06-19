from datetime import date, timedelta
from pathlib import Path

import app as app_module
from database.models import db, OP, OPSetor, Tarefa
from tempo import hoje_brasilia


def criar_tarefa_slide(
    nome_op,
    nome_tarefa,
    setor,
    prazo,
    status_op="EM ANDAMENTO",
    cliente=None,
):
    op = OP(
        nome=nome_op,
        cliente=cliente,
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


def slides_por_prefixo(dados, prefixo):
    return [
        slide
        for slide in dados["slides"]
        if slide["id"] == prefixo or slide["id"].startswith(f"{prefixo}-")
    ]


def slides_de_lista(dados):
    return [
        slide
        for slide in dados["slides"]
        if slide["tipo"] == "lista"
    ]


def test_slides_exige_login(client):
    resposta = client.get("/slides")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")


def test_slides_espectador_acessa(client, login_as):
    login_as("ESPECTADOR")

    resposta = client.get("/slides")

    assert resposta.status_code == 200
    assert "Painel de entregas" in resposta.get_data(as_text=True)


def test_slides_renderiza_botoes_de_navegacao_no_footer(client, login_as):
    login_as("ESPECTADOR")

    resposta = client.get("/slides")
    html = resposta.get_data(as_text=True)
    inicio_footer = html.index('<footer class="tv-footer">')
    fim_footer = html.index("</footer>", inicio_footer)
    footer = html[inicio_footer:fim_footer]

    assert resposta.status_code == 200
    assert "data-slide-prev" in footer
    assert "data-slide-next" in footer
    assert "tv-nav-button-prev" not in html
    assert "tv-nav-button-next" not in html


def test_slides_versiona_assets_para_evitar_cache_visual(client, login_as):
    login_as("ESPECTADOR")

    resposta = client.get("/slides")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "css/slides.css?v=" in html
    assert "js/slides.js?v=" in html


def test_slides_js_relogio_usa_timezone_brasilia():
    js = Path("static/js/slides.js").read_text(encoding="utf-8")

    assert 'toLocaleTimeString("pt-BR"' in js
    assert 'timeZone: "America/Sao_Paulo"' in js


def test_slides_setor_acessa(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/slides")

    assert resposta.status_code == 200
    assert "Painel de entregas" in resposta.get_data(as_text=True)


def test_api_slides_reaproveita_cache_dentro_do_ttl(client, login_as, monkeypatch):
    chamadas = []

    def montar_payload_fake(setor_id=None):
        chamadas.append(setor_id)
        return {
            "slides": [{"id": f"slide-{len(chamadas)}"}],
            "resumo": {},
            "categorias": {},
            "intervalos": {},
        }

    monkeypatch.setenv("SLIDES_CACHE_TTL_SECONDS", "60")
    monkeypatch.setattr(
        app_module.slides_routes_module,
        "montar_payload_slides",
        montar_payload_fake,
    )
    login_as("ADMIN")

    primeira = client.get("/api/slides").get_json()
    segunda = client.get("/api/slides").get_json()

    assert chamadas == [None]
    assert primeira == segunda


def test_api_slides_commit_externo_nao_invalida_cache(client, login_as, monkeypatch):
    chamadas = []

    def montar_payload_fake(setor_id=None):
        chamadas.append(setor_id)
        return {
            "slides": [{"id": f"slide-{len(chamadas)}"}],
            "resumo": {},
            "categorias": {},
            "intervalos": {},
        }

    monkeypatch.setenv("SLIDES_CACHE_TTL_SECONDS", "60")
    monkeypatch.setattr(
        app_module.slides_routes_module,
        "montar_payload_slides",
        montar_payload_fake,
    )
    login_as("ADMIN")

    primeira = client.get("/api/slides").get_json()
    db.session.commit()
    segunda = client.get("/api/slides").get_json()

    assert chamadas == [None]
    assert primeira == segunda


def test_api_slides_ttl_zero_desativa_cache(client, login_as, monkeypatch):
    chamadas = []

    def montar_payload_fake(setor_id=None):
        chamadas.append(setor_id)
        return {
            "slides": [{"id": f"slide-{len(chamadas)}"}],
            "resumo": {},
            "categorias": {},
            "intervalos": {},
        }

    monkeypatch.setenv("SLIDES_CACHE_TTL_SECONDS", "0")
    monkeypatch.setattr(
        app_module.slides_routes_module,
        "montar_payload_slides",
        montar_payload_fake,
    )
    login_as("ADMIN")

    primeira = client.get("/api/slides").get_json()
    segunda = client.get("/api/slides").get_json()

    assert chamadas == [None, None]
    assert primeira != segunda


def test_api_slides_ttl_expirado_remonta_payload(client, login_as, monkeypatch):
    chamadas = []
    tempos = iter([100.0, 161.0])

    def montar_payload_fake(setor_id=None):
        chamadas.append(setor_id)
        return {
            "slides": [{"id": f"slide-{len(chamadas)}"}],
            "resumo": {},
            "categorias": {},
            "intervalos": {},
        }

    monkeypatch.setenv("SLIDES_CACHE_TTL_SECONDS", "60")
    monkeypatch.setattr(
        app_module.slides_routes_module.time,
        "monotonic",
        lambda: next(tempos),
    )
    monkeypatch.setattr(
        app_module.slides_routes_module,
        "montar_payload_slides",
        montar_payload_fake,
    )
    login_as("ADMIN")

    primeira = client.get("/api/slides").get_json()
    segunda = client.get("/api/slides").get_json()

    assert chamadas == [None, None]
    assert primeira != segunda


def test_api_slides_setor_ve_apenas_tarefas_do_proprio_setor(client, login_as, setores):
    hoje = hoje_brasilia()
    criar_tarefa_slide(
        "OP Slide Acabamento",
        "Tarefa slide acabamento",
        setores["Acabamento"],
        hoje,
    )
    criar_tarefa_slide(
        "OP Slide PCP",
        "Tarefa slide pcp",
        setores["PCP"],
        hoje,
    )
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/api/slides")
    dados = resposta.get_json()

    assert resposta.status_code == 200
    assert "Tarefa slide acabamento" in nomes_itens(dados["categorias"]["hoje"])
    assert "Tarefa slide pcp" not in nomes_itens(dados["categorias"]["hoje"])


def test_api_slides_retorna_categorias(client, login_as, setores):
    criar_tarefa_slide(
        "OP API Slides",
        "Tarefa API Slides",
        setores["Acabamento"],
        hoje_brasilia(),
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
    assert all(
        slide["tipo"] == "lista"
        for slide in dados["slides"]
        if slide["id"].startswith("setor-")
    )


def test_api_slides_retorna_cliente_da_op_na_tarefa(client, login_as, setores):
    criar_tarefa_slide(
        "OP Cliente Slides",
        "Tarefa cliente slides",
        setores["Acabamento"],
        hoje_brasilia(),
        cliente="Cliente Slides",
    )
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    itens_por_nome = {
        item["tarefa"]: item
        for item in dados["categorias"]["hoje"]
    }

    assert itens_por_nome["Tarefa cliente slides"]["cliente"] == "Cliente Slides"


def test_api_slides_cliente_vazio_retorna_nao_informado(client, login_as, setores):
    criar_tarefa_slide(
        "OP Sem Cliente Slides",
        "Tarefa sem cliente slides",
        setores["Acabamento"],
        hoje_brasilia(),
        cliente="",
    )
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    itens_por_nome = {
        item["tarefa"]: item
        for item in dados["categorias"]["hoje"]
    }

    assert itens_por_nome["Tarefa sem cliente slides"]["cliente"] == "Não informado"


def test_api_slides_nao_exibe_arquivadas_ou_finalizadas(client, login_as, setores):
    hoje = hoje_brasilia()
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


def test_api_slides_exibe_entregue_nao_validada_e_oculta_validada(client, login_as, setores):
    hoje = hoje_brasilia()
    _, tarefa_validacao = criar_tarefa_slide(
        "OP Em Validacao",
        "Tarefa aguardando validacao",
        setores["Acabamento"],
        hoje,
    )
    tarefa_validacao.entregue = True
    tarefa_validacao.validado = False
    tarefa_validacao.status = "EM VALIDAÇÃO"

    _, tarefa_validada = criar_tarefa_slide(
        "OP Validada",
        "Tarefa ja validada",
        setores["Acabamento"],
        hoje,
    )
    tarefa_validada.entregue = True
    tarefa_validada.validado = True
    tarefa_validada.status = "ENTREGUE"
    db.session.commit()
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    itens_hoje = dados["categorias"]["hoje"]
    itens_por_nome = {item["tarefa"]: item for item in itens_hoje}

    assert itens_por_nome["Tarefa aguardando validacao"]["status"] == "EM VALIDAÇÃO"
    assert "Tarefa ja validada" not in itens_por_nome


def test_api_slides_classifica_atrasada_hoje_amanha_e_15_dias(client, login_as, setores):
    hoje = hoje_brasilia()
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


def test_api_slides_usa_data_brasilia_para_classificar_prazos(
    client,
    login_as,
    setores,
    monkeypatch,
):
    hoje = date(2026, 5, 21)
    monkeypatch.setattr(
        app_module.slides_routes_module,
        "hoje_brasilia",
        lambda: hoje,
    )

    criar_tarefa_slide("OP BSB Atrasada", "BSB atrasada", setores["Acabamento"], hoje - timedelta(days=1))
    criar_tarefa_slide("OP BSB Hoje", "BSB hoje", setores["Acabamento"], hoje)
    criar_tarefa_slide("OP BSB Amanha", "BSB amanha", setores["Acabamento"], hoje + timedelta(days=1))
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()

    assert dados["atualizado_em"] == "2026-05-21"
    assert "BSB atrasada" in nomes_itens(dados["categorias"]["atrasadas"])
    assert "BSB hoje" in nomes_itens(dados["categorias"]["hoje"])
    assert "BSB amanha" in nomes_itens(dados["categorias"]["amanha"])


def test_api_slides_categoria_com_7_tarefas_gera_2_slides(client, login_as, setores):
    hoje = hoje_brasilia()
    for indice in range(7):
        criar_tarefa_slide(
            f"OP Atrasada {indice}",
            f"Tarefa atrasada {indice}",
            setores["Acabamento"],
            hoje - timedelta(days=1),
        )
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    slides_atrasadas = slides_por_prefixo(dados, "atrasadas")

    assert len(slides_atrasadas) == 2
    assert slides_atrasadas[0]["titulo"] == "Tarefas atrasadas 1/2"
    assert slides_atrasadas[1]["titulo"] == "Tarefas atrasadas 2/2"
    assert [len(slide["itens"]) for slide in slides_atrasadas] == [5, 2]


def test_api_slides_lista_tem_no_maximo_5_itens(client, login_as, setores):
    hoje = hoje_brasilia()
    for indice in range(7):
        criar_tarefa_slide(
            f"OP Hoje {indice}",
            f"Tarefa hoje {indice}",
            setores["Acabamento"],
            hoje,
        )
    login_as("PCP")

    dados = client.get("/api/slides").get_json()

    assert all(len(slide["itens"]) <= 5 for slide in slides_de_lista(dados))


def test_api_slides_categoria_vazia_nao_gera_slide_exceto_atrasadas(client, login_as):
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    ids = {slide["id"] for slide in dados["slides"]}

    assert "resumo" in ids
    assert "atrasadas" in ids
    assert "hoje" not in ids
    assert "amanha" not in ids
    assert "proximos-15" not in ids
    assert not any(id_slide.startswith("setor-") for id_slide in ids)


def test_api_slides_sem_atrasadas_gera_slide_de_parabens(client, login_as):
    login_as("ATENDENTE")

    dados = client.get("/api/slides").get_json()
    slide_atrasadas = slides_por_prefixo(dados, "atrasadas")[0]

    assert slide_atrasadas["itens"] == []
    assert slide_atrasadas["vazio"] == "Não há tarefas em atraso, parabéns!"


def test_api_slides_intervalos_do_painel(client, login_as):
    login_as("ESPECTADOR")

    dados = client.get("/api/slides").get_json()

    assert dados["intervalos"]["slide_ms"] == 8000
    assert dados["intervalos"]["atualizacao_ms"] == 90000


def test_api_slides_setor_pagina_corretamente(client, login_as, setores):
    hoje = hoje_brasilia()
    for indice in range(7):
        criar_tarefa_slide(
            f"OP Setor {indice}",
            f"Tarefa setor {indice}",
            setores["PCP"],
            hoje + timedelta(days=16),
        )
    login_as("ADMIN")

    dados = client.get("/api/slides").get_json()
    slides_setor = slides_por_prefixo(dados, "setor-pcp")

    assert len(slides_setor) == 2
    assert [len(slide["itens"]) for slide in slides_setor] == [5, 2]
