def test_health_nao_exige_banco(client):
    resposta = client.get("/health")

    assert resposta.status_code == 200
    assert resposta.get_json() == {"status": "ok"}


def test_db_health_executa_select_minimo(client):
    resposta = client.get("/db-health")
    dados = resposta.get_json()

    assert resposta.status_code == 200
    assert dados["status"] == "ok"
    assert dados["db"] == "ok"
    assert isinstance(dados["elapsed_ms"], int)
    assert dados["elapsed_ms"] >= 0
