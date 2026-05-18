from datetime import datetime, timedelta

from database.models import db, OP, OPSetor, Setor, Tarefa


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


def test_metricas_permite_admin_atendente_e_pcp(client, login_as):
    for tipo in ["ADMIN", "ATENDENTE", "PCP"]:
        login_as(tipo)

        resposta = client.get("/metricas")

        assert resposta.status_code == 200
        assert "Métricas" in resposta.get_data(as_text=True)


def test_metricas_bloqueia_setor(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/metricas")

    assert resposta.status_code == 403
    assert b"Acesso negado" in resposta.data


def test_navbar_esconde_metricas_para_setor(client, login_as, setores):
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = client.get("/dashboard")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Métricas" not in html


def test_metricas_renderiza_contagens_tempos_e_gargalos(client, login_as, setores):
    acabamento = setores["Acabamento"]
    pcp = setores["PCP"]
    agora = datetime(2026, 5, 18, 9, 0)

    op_andamento = OP(
        nome="OP Métricas Andamento",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        criada_em=agora - timedelta(days=5),
    )
    op_finalizada = OP(
        nome="OP Métricas Finalizada",
        status="FINALIZADA",
        atendente="atendente@teste.com",
        criada_em=agora - timedelta(days=4),
        finalizada_em=agora - timedelta(days=1),
    )
    db.session.add_all([op_andamento, op_finalizada])
    db.session.flush()

    db.session.add_all([
        OPSetor(op_id=op_andamento.id, setor_id=acabamento.id),
        OPSetor(op_id=op_finalizada.id, setor_id=pcp.id),
    ])

    criar_tarefa_metricas(
        op_andamento,
        acabamento,
        "Pendente métricas",
        "PENDENTE",
        agora - timedelta(days=3),
    )
    criar_tarefa_metricas(
        op_andamento,
        acabamento,
        "Produção métricas",
        "EM ANDAMENTO",
        agora - timedelta(days=3),
        iniciada_em=agora - timedelta(days=2),
    )
    criar_tarefa_metricas(
        op_andamento,
        acabamento,
        "Validação métricas",
        "EM VALIDAÇÃO",
        agora - timedelta(days=4),
        iniciada_em=agora - timedelta(days=3),
        enviada_validacao_em=agora - timedelta(days=1),
        entregue=True,
    )
    criar_tarefa_metricas(
        op_finalizada,
        pcp,
        "Entregue métricas",
        "ENTREGUE",
        agora - timedelta(days=5),
        iniciada_em=agora - timedelta(days=4),
        enviada_validacao_em=agora - timedelta(days=2),
        validada_em=agora - timedelta(days=1),
        concluida_em=agora - timedelta(days=1),
        entregue=True,
        validado=True,
    )
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get("/metricas")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "PENDENTE" in html
    assert "EM ANDAMENTO" in html
    assert "EM VALIDAÇÃO" in html
    assert "ENTREGUE" in html
    assert "Acabamento" in html
    assert "PCP" in html
    assert "2.0 dias" in html
    assert "3.0 dias" in html
