def html(response):
    return response.get_data(as_text=True)


def test_metricas_carrega_theme_css_versionado(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/metricas")

    assert resposta.status_code == 200
    assert "css/theme.css?v=" in html(resposta)


def test_dashboard_carrega_assets_versionados(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/dashboard")
    conteudo = html(resposta)

    assert resposta.status_code == 200
    assert "css/theme.css?v=" in conteudo
    assert "css/dashboard.css?v=" in conteudo
    assert "js/password_toggle.js?v=" in conteudo


def test_op_carrega_theme_css_versionado(client, login_as, op_com_setor):
    op, _setor = op_com_setor
    login_as("ADMIN")

    resposta = client.get(f"/op/{op.id}")

    assert resposta.status_code == 200
    assert "css/theme.css?v=" in html(resposta)


def test_usuarios_carrega_theme_css_versionado(client, login_as):
    login_as("ADMIN")

    resposta = client.get("/usuarios")

    assert resposta.status_code == 200
    assert "css/theme.css?v=" in html(resposta)


def test_slides_mantem_versionamento_proprio(client, login_as):
    login_as("ESPECTADOR")

    resposta = client.get("/slides")
    conteudo = html(resposta)

    assert resposta.status_code == 200
    assert "css/slides.css?v=" in conteudo
    assert "js/slides.js?v=" in conteudo
    assert "asset_version(" not in conteudo
