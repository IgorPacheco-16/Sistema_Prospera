from datetime import timedelta

import pytest

from database.models import db, HistoricoOP, Notificacao, Tarefa, TarefaEsperaSolicitacao, User
from tempo import hoje_brasilia


def criar_usuario(email, setor, nome=None, tipo="SETOR", ativo=True):
    usuario = User(
        nome=nome or email,
        email=email,
        senha="123",
        tipo=tipo,
        setor_id=setor.id if setor else None,
        ativo=ativo,
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def atribuir(tarefa, usuarios):
    tarefa.responsaveis = usuarios
    db.session.commit()


def solicitar(client, tarefa, motivo="Aguardando arquivo final"):
    return client.post(
        f"/tarefas/{tarefa.id}/espera/solicitar",
        data={"motivo": motivo},
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )


def aprovar(client, solicitacao):
    return client.post(
        f"/tarefas/espera/{solicitacao.id}/aprovar",
        headers={"Referer": f"/op/{solicitacao.tarefa.op_id}"},
    )


def recusar(client, solicitacao, justificativa="Prioridade mantida"):
    return client.post(
        f"/tarefas/espera/{solicitacao.id}/recusar",
        data={"justificativa_resposta": justificativa},
        headers={"Referer": f"/op/{solicitacao.tarefa.op_id}"},
    )


def solicitacao_da_tarefa(tarefa):
    return TarefaEsperaSolicitacao.query.filter_by(tarefa_id=tarefa.id).first()


def preparar_solicitacao(client, login_as, tarefa):
    responsavel = criar_usuario("espera.responsavel@teste.com", tarefa.setor, "Resp Espera")
    atribuir(tarefa, [responsavel])
    login_as("SETOR", email=responsavel.email, setor_id=tarefa.setor_id)
    resposta = solicitar(client, tarefa)
    assert resposta.status_code == 302
    return solicitacao_da_tarefa(tarefa), responsavel


def test_usuario_responsavel_consegue_solicitar_espera_com_motivo(client, login_as, tarefa):
    responsavel = criar_usuario("responsavel.espera@teste.com", tarefa.setor, "Responsavel Espera")
    atribuir(tarefa, [responsavel])
    login_as("SETOR", email=responsavel.email, setor_id=tarefa.setor_id)

    resposta = solicitar(client, tarefa, "Falta arquivo final")
    solicitacao = solicitacao_da_tarefa(tarefa)

    assert resposta.status_code == 302
    assert solicitacao is not None
    assert solicitacao.status == "PENDENTE"
    assert solicitacao.motivo == "Falta arquivo final"
    db.session.refresh(tarefa)
    assert tarefa.status == "PENDENTE"
    assert tarefa.em_espera is False
    assert Notificacao.query.filter_by(
        usuario="PCP",
        tarefa_id=tarefa.id,
        tipo_evento=f"tarefa_espera_solicitada_{solicitacao.id}",
    ).first()
    assert Notificacao.query.filter_by(
        usuario="atendente@teste.com",
        tarefa_id=tarefa.id,
        tipo_evento=f"tarefa_espera_solicitada_{solicitacao.id}",
    ).first()
    assert HistoricoOP.query.filter_by(op_id=tarefa.op_id, acao="Espera solicitada").first()


def test_setor_nao_consegue_solicitar_espera_em_tarefa_de_outro_setor(client, login_as, tarefa, setores):
    login_as("SETOR", setor_id=setores["PCP"].id)

    resposta = solicitar(client, tarefa, "Tentativa fora do setor")

    assert resposta.status_code == 403
    assert "Acesso negado para solicitar espera" in resposta.get_data(as_text=True)
    assert TarefaEsperaSolicitacao.query.count() == 0


def test_nao_permite_solicitar_espera_sem_motivo(client, login_as, tarefa):
    login_as("ADMIN")

    resposta = solicitar(client, tarefa, "")

    assert resposta.status_code == 400
    assert "Motivo obrigatorio" in resposta.get_data(as_text=True)
    assert TarefaEsperaSolicitacao.query.count() == 0


def test_nao_permite_duas_solicitacoes_pendentes_para_mesma_tarefa(client, login_as, tarefa):
    login_as("ADMIN")
    assert solicitar(client, tarefa, "Falta briefing").status_code == 302

    resposta = solicitar(client, tarefa, "Falta aprovacao")

    assert resposta.status_code == 400
    assert TarefaEsperaSolicitacao.query.filter_by(tarefa_id=tarefa.id).count() == 1


@pytest.mark.parametrize("tipo", ["PCP", "ATENDENTE", "ADMIN"])
def test_gestao_consegue_aprovar_solicitacao(client, login_as, tarefa, tipo):
    solicitacao, responsavel = preparar_solicitacao(client, login_as, tarefa)
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    login_as(tipo)

    resposta = aprovar(client, solicitacao)
    db.session.refresh(tarefa)
    db.session.refresh(solicitacao)

    assert resposta.status_code == 302
    assert tarefa.status == "EM ESPERA"
    assert tarefa.em_espera is True
    assert tarefa.espera_motivo_atual == "Aguardando arquivo final"
    assert tarefa.espera_solicitacao_atual_id == solicitacao.id
    assert solicitacao.status == "APROVADA"
    assert solicitacao.status_anterior_tarefa == "PENDENTE"
    assert Notificacao.query.filter_by(
        usuario=responsavel.email,
        tarefa_id=tarefa.id,
        tipo_evento=f"tarefa_espera_aprovada_{solicitacao.id}",
    ).first()


def test_usuario_sem_permissao_nao_consegue_aprovar(client, login_as, tarefa):
    solicitacao, responsavel = preparar_solicitacao(client, login_as, tarefa)
    login_as("SETOR", email=responsavel.email, setor_id=tarefa.setor_id)

    resposta = aprovar(client, solicitacao)
    db.session.refresh(tarefa)

    assert resposta.status_code == 403
    assert tarefa.status == "PENDENTE"


def test_recusar_solicitacao_mantem_status_anterior_e_notifica(client, login_as, tarefa):
    solicitacao, responsavel = preparar_solicitacao(client, login_as, tarefa)
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    login_as("PCP")

    resposta = recusar(client, solicitacao, "Executar mesmo sem arquivo final")
    db.session.refresh(tarefa)
    db.session.refresh(solicitacao)

    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"
    assert tarefa.em_espera is False
    assert solicitacao.status == "RECUSADA"
    assert solicitacao.justificativa_resposta == "Executar mesmo sem arquivo final"
    assert Notificacao.query.filter_by(
        usuario=responsavel.email,
        tarefa_id=tarefa.id,
        tipo_evento=f"tarefa_espera_recusada_{solicitacao.id}",
    ).first()
    assert HistoricoOP.query.filter_by(op_id=tarefa.op_id, acao="Espera recusada").first()


def test_retomar_tarefa_em_espera_restaura_status_anterior(client, login_as, tarefa):
    tarefa.status = "EM ANDAMENTO"
    db.session.commit()
    solicitacao, _responsavel = preparar_solicitacao(client, login_as, tarefa)
    login_as("ADMIN")
    aprovar(client, solicitacao)

    resposta = client.post(
        f"/tarefas/{tarefa.id}/espera/retomar",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    db.session.refresh(tarefa)

    assert resposta.status_code == 302
    assert tarefa.status == "EM ANDAMENTO"
    assert tarefa.em_espera is False
    assert tarefa.espera_solicitacao_atual_id is None
    assert HistoricoOP.query.filter_by(op_id=tarefa.op_id, acao="Tarefa retomada").first()


def test_tarefa_em_espera_aparece_no_detalhe_da_op(client, login_as, tarefa):
    solicitacao, _responsavel = preparar_solicitacao(client, login_as, tarefa)
    login_as("PCP")
    aprovar(client, solicitacao)

    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)

    assert "EM ESPERA" in html
    assert "Aguardando arquivo final" in html
    assert f'action="/tarefas/{tarefa.id}/espera/retomar"' in html


def test_solicitacao_pendente_aparece_no_card_da_tarefa(client, login_as, tarefa):
    preparar_solicitacao(client, login_as, tarefa)
    login_as("PCP")

    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)

    assert "Solicita&ccedil;&atilde;o de espera pendente" in html
    assert "Aguardando arquivo final" in html
    assert "Aprovar espera" in html


def test_tarefa_em_espera_aparece_no_kanban_e_calendario(client, login_as, tarefa):
    tarefa.prazo = hoje_brasilia() - timedelta(days=2)
    db.session.commit()
    solicitacao, _responsavel = preparar_solicitacao(client, login_as, tarefa)
    login_as("ADMIN")
    aprovar(client, solicitacao)

    kanban = client.get("/kanban").get_data(as_text=True)
    calendario = client.get("/calendario").get_data(as_text=True)

    assert "Em espera" in kanban
    assert "Motivo da espera: Aguardando arquivo final" in kanban
    assert "Em espera" in calendario
    assert "Aguardando arquivo final" in calendario


def test_tarefa_em_espera_nao_conta_como_atrasada_em_metricas(client, login_as, tarefa):
    tarefa.prazo = hoje_brasilia() - timedelta(days=2)
    db.session.commit()
    solicitacao, _responsavel = preparar_solicitacao(client, login_as, tarefa)
    login_as("ADMIN")
    aprovar(client, solicitacao)

    html = client.get("/metricas").get_data(as_text=True)
    atrasadas_bloco = html[
        html.index('data-metricas-kpi="atrasadas"'):
        html.index('data-metricas-kpi="recusadas"')
    ]

    assert "EM ESPERA" in html
    assert "<strong>0</strong>" in atrasadas_bloco


def test_espera_nao_quebra_validacao_repasse_ou_responsaveis(client, login_as, tarefa):
    responsavel = criar_usuario("espera.repasse@teste.com", tarefa.setor, "Resp Repasse")
    novo = criar_usuario("espera.novo@teste.com", tarefa.setor, "Novo Resp")
    atribuir(tarefa, [responsavel])
    login_as("ADMIN")
    solicitar(client, tarefa, "Aguardando insumo")
    solicitacao = solicitacao_da_tarefa(tarefa)
    aprovar(client, solicitacao)

    resposta_repasse = client.post(
        f"/tarefas/{tarefa.id}/responsaveis",
        data={"usuario_ids": [str(novo.id)], "tipo": "INCLUSAO"},
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    resposta_validacao = client.post(
        f"/validar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )

    db.session.refresh(tarefa)
    assert resposta_repasse.status_code == 302
    assert resposta_validacao.status_code == 400
    assert sorted(usuario.email for usuario in tarefa.responsaveis) == [responsavel.email]
