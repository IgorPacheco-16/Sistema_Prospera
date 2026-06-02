import pytest

from database.models import db, OP, OPSetor, Tarefa, TarefaObservacao, User
from tempo import agora_brasilia


def postar_observacao(client, tarefa, texto="Material aguardando liberacao"):
    return client.post(
        f"/tarefas/{tarefa.id}/observacoes",
        data={"texto": texto},
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )


@pytest.mark.parametrize("tipo", ["ADMIN", "PCP", "ATENDENTE", "SETOR"])
def test_usuarios_autorizados_adicionam_observacao(client, login_as, tarefa, tipo):
    if tipo == "SETOR":
        login_as(tipo, setor_id=tarefa.setor_id)
    else:
        login_as(tipo)

    resposta = postar_observacao(client, tarefa, "Cliente pediu ajuste no layout.")
    observacao = TarefaObservacao.query.one()

    assert resposta.status_code == 302
    assert observacao.tarefa_id == tarefa.id
    assert observacao.texto == "Cliente pediu ajuste no layout."
    assert observacao.autor.email in {
        "admin@teste.com",
        "pcp@teste.com",
        "atendente@teste.com",
        "setor@teste.com",
    }
    assert observacao.criada_em is not None
    assert observacao.deletada_em is None


def test_espectador_nao_adiciona_observacao(client, login_as, tarefa):
    login_as("ESPECTADOR")

    resposta = postar_observacao(client, tarefa)

    assert resposta.status_code == 403
    assert TarefaObservacao.query.count() == 0


def test_setor_nao_adiciona_observacao_em_tarefa_sem_acesso(client, login_as, op_com_setor, setores):
    op, _acabamento = op_com_setor
    setor_pcp = setores["PCP"]
    db.session.add(OPSetor(op_id=op.id, setor_id=setor_pcp.id))
    tarefa_pcp = Tarefa(
        op_id=op.id,
        setor_id=setor_pcp.id,
        nome="Tarefa de outro setor",
        status="PENDENTE",
        liberada=True,
    )
    db.session.add(tarefa_pcp)
    db.session.commit()

    login_as("SETOR", setor_id=setores["Acabamento"].id)
    resposta = postar_observacao(client, tarefa_pcp)

    assert resposta.status_code == 403
    assert TarefaObservacao.query.count() == 0


def test_nao_aceita_observacao_vazia_ou_acima_do_limite(client, login_as, tarefa):
    login_as("ADMIN")

    vazia = postar_observacao(client, tarefa, "   ")
    longa = postar_observacao(client, tarefa, "x" * 1001)

    assert vazia.status_code == 400
    assert longa.status_code == 400
    assert TarefaObservacao.query.count() == 0


def test_nao_adiciona_observacao_em_tarefa_inexistente(client, login_as):
    login_as("ADMIN")

    resposta = client.post("/tarefas/999999/observacoes", data={"texto": "Teste"})

    assert resposta.status_code == 404


def test_nao_adiciona_observacao_em_op_finalizada_ou_arquivada(client, login_as, tarefa):
    login_as("ADMIN")
    op = db.session.get(OP, tarefa.op_id)

    op.status = "FINALIZADA"
    op.finalizada_em = agora_brasilia()
    db.session.commit()
    finalizada = postar_observacao(client, tarefa, "Arquivo revisado e aprovado.")

    op.status = "ARQUIVADA"
    op.finalizada_em = None
    op.arquivada_em = agora_brasilia()
    db.session.commit()
    arquivada = postar_observacao(client, tarefa, "Aguardando retorno do atendimento.")

    assert finalizada.status_code == 400
    assert arquivada.status_code == 400
    assert TarefaObservacao.query.count() == 0


def test_detalhe_exibe_historico_com_autor_data_e_html_escapado(client, login_as, tarefa):
    admin = User.query.filter_by(email="admin@teste.com").first()
    observacao = TarefaObservacao(
        tarefa_id=tarefa.id,
        autor_id=admin.id,
        texto="<img src=x onerror=alert(1)>",
        criada_em=agora_brasilia(),
    )
    db.session.add(observacao)
    db.session.commit()
    login_as("ADMIN")

    resposta = client.get(f"/op/{tarefa.op_id}")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Observacoes" in html
    assert "admin@teste.com" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert f'action="/tarefas/observacoes/{observacao.id}/excluir"' in html


def test_admin_exclui_observacao_com_soft_delete(client, login_as, tarefa):
    observacao = TarefaObservacao(
        tarefa_id=tarefa.id,
        autor_id=User.query.filter_by(email="pcp@teste.com").first().id,
        texto="Arquivo revisado e aprovado.",
        criada_em=agora_brasilia(),
    )
    db.session.add(observacao)
    db.session.commit()
    login_as("ADMIN")

    resposta = client.post(
        f"/tarefas/observacoes/{observacao.id}/excluir",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    db.session.refresh(observacao)
    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)

    assert resposta.status_code == 302
    assert observacao.deletada_em is not None
    assert observacao.deletada_por.email == "admin@teste.com"
    assert "Arquivo revisado e aprovado." not in html


def test_apenas_admin_exclui_observacao(client, login_as, tarefa):
    observacao = TarefaObservacao(
        tarefa_id=tarefa.id,
        autor_id=User.query.filter_by(email="pcp@teste.com").first().id,
        texto="Aguardando retorno do atendimento.",
        criada_em=agora_brasilia(),
    )
    db.session.add(observacao)
    db.session.commit()
    login_as("PCP")

    resposta = client.post(f"/tarefas/observacoes/{observacao.id}/excluir")
    db.session.refresh(observacao)

    assert resposta.status_code == 403
    assert observacao.deletada_em is None
