from datetime import timedelta

from database.models import db, Notificacao, OP, OPSetor, Setor, Tarefa, TarefaSolicitacao, User
from tempo import agora_brasilia, hoje_brasilia


def criar_setor_destino(op, nome="Impressao"):
    setor = Setor(nome=nome)
    db.session.add(setor)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    db.session.commit()
    return setor


def solicitar(client, op, setor_destino, nome="Separar insumo", justificativa="Precisa de apoio"):
    return client.post(
        f"/ops/{op.id}/solicitacoes-tarefa",
        data={
            "setor_destino_id": str(setor_destino.id),
            "nome": nome,
            "justificativa": justificativa,
            "prazo_sugerido": (hoje_brasilia() + timedelta(days=1)).strftime("%Y-%m-%d"),
        },
        headers={"Referer": f"/op/{op.id}"},
    )


def solicitacao_unica():
    return TarefaSolicitacao.query.one()


def test_setor_autorizado_consegue_solicitar_tarefa_em_op_acessivel(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)

    resposta = solicitar(client, op, destino)

    assert resposta.status_code == 302
    solicitacao = solicitacao_unica()
    assert solicitacao.status == "PENDENTE"
    assert solicitacao.setor_solicitante_id == setor_origem.id
    assert solicitacao.setor_destino_id == destino.id
    assert Tarefa.query.count() == 0
    assert Notificacao.query.filter_by(
        usuario="PCP",
        op_id=op.id,
        setor_id=destino.id,
        tipo_evento=f"tarefa_solicitacao_criada_{solicitacao.id}",
    ).first()


def test_setor_nao_consegue_solicitar_em_op_que_nao_acessa(client, login_as, setores):
    op = OP(nome="OP Sem Acesso", status="EM ANDAMENTO", atendente="atendente@teste.com")
    db.session.add(op)
    db.session.flush()
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setores["Acabamento"].id)

    resposta = solicitar(client, op, destino)

    assert resposta.status_code == 403
    assert TarefaSolicitacao.query.count() == 0


def test_espectador_nao_consegue_solicitar_tarefa(client, login_as, op_com_setor):
    op, _setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("ESPECTADOR")

    resposta = solicitar(client, op, destino)

    assert resposta.status_code == 403
    assert TarefaSolicitacao.query.count() == 0


def test_nao_permite_solicitacao_em_op_finalizada_ou_arquivada(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)

    op.status = "FINALIZADA"
    op.finalizada_em = agora_brasilia()
    db.session.commit()
    assert solicitar(client, op, destino).status_code == 403

    op.status = "ARQUIVADA"
    op.finalizada_em = None
    op.arquivada_em = agora_brasilia()
    db.session.commit()
    assert solicitar(client, op, destino).status_code == 403
    assert TarefaSolicitacao.query.count() == 0


def test_nao_permite_solicitacao_sem_descricao_ou_justificativa(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)

    sem_descricao = solicitar(client, op, destino, nome="")
    sem_justificativa = solicitar(client, op, destino, justificativa="")

    assert sem_descricao.status_code == 400
    assert sem_justificativa.status_code == 400
    assert TarefaSolicitacao.query.count() == 0


def test_solicitacao_pendente_nao_conta_no_progresso_e_nao_tem_acoes_operacionais(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    login_as("PCP")
    html = client.get(f"/op/{op.id}").get_data(as_text=True)

    assert "0/0 tarefas" in html
    assert "Aguardando aprova" in html
    assert f'action="/iniciar_tarefa/{solicitacao.id}"' not in html
    assert f'action="/entregar_tarefa/{solicitacao.id}"' not in html
    assert f'action="/validar_tarefa/{solicitacao.id}"' not in html
    assert Tarefa.query.count() == 0


def test_solicitacao_pendente_nao_pode_ser_acionada_por_rotas_operacionais(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    login_as("PCP")
    assert client.post(f"/iniciar_tarefa/{solicitacao.id}").status_code == 404
    assert client.post(f"/entregar_tarefa/{solicitacao.id}").status_code == 404
    assert client.post(f"/validar_tarefa/{solicitacao.id}").status_code == 404
    assert client.post(f"/recusar_tarefa/{solicitacao.id}", data={"motivo_recusa": "x"}).status_code == 404


def test_solicitacao_pendente_nao_entra_no_relatorio_operacional(client, login_as, op_com_setor):
    import app as app_module

    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino, nome="Pedido fora do relatorio")

    usuario_setor = User.query.filter_by(email="setor@teste.com").first()
    relatorio = app_module.relatorio_module.montar_relatorio_usuario(usuario_setor, "10h")
    texto = "\n".join(
        item.texto
        for itens in relatorio.secoes.values()
        for item in itens
    )

    assert "Pedido fora do relatorio" not in texto


def test_pcp_consegue_aprovar_e_notifica_solicitante_e_setor_destino(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    login_as("PCP")
    resposta = client.post(
        f"/tarefas/solicitacoes/{solicitacao.id}/aprovar",
        headers={"Referer": f"/op/{op.id}"},
    )

    assert resposta.status_code == 302
    db.session.refresh(solicitacao)
    tarefa = Tarefa.query.one()
    assert solicitacao.status == "APROVADA"
    assert solicitacao.tarefa_id == tarefa.id
    assert tarefa.nome == solicitacao.nome
    assert tarefa.setor_id == destino.id
    assert tarefa.status == "PENDENTE"
    assert Notificacao.query.filter_by(
        usuario="setor@teste.com",
        tipo_evento=f"tarefa_solicitacao_aprovada_{solicitacao.id}",
    ).first()
    assert Notificacao.query.filter_by(
        usuario="SETOR",
        setor_id=destino.id,
        tarefa_id=tarefa.id,
        tipo_evento=f"tarefa_criada_solicitacao_{solicitacao.id}",
    ).first()


def test_admin_consegue_aprovar_solicitacao(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    login_as("ADMIN")
    resposta = client.post(f"/tarefas/solicitacoes/{solicitacao.id}/aprovar")

    assert resposta.status_code == 302
    assert Tarefa.query.count() == 1


def test_setor_nao_consegue_aprovar_solicitacao(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    resposta = client.post(f"/tarefas/solicitacoes/{solicitacao.id}/aprovar")

    assert resposta.status_code == 403
    assert Tarefa.query.count() == 0


def test_pcp_consegue_recusar_sem_criar_tarefa_e_notifica_solicitante(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    login_as("PCP")
    resposta = client.post(
        f"/tarefas/solicitacoes/{solicitacao.id}/recusar",
        data={"justificativa_resposta": "Nao necessario agora"},
    )

    assert resposta.status_code == 302
    db.session.refresh(solicitacao)
    assert solicitacao.status == "RECUSADA"
    assert Tarefa.query.count() == 0
    assert Notificacao.query.filter_by(
        usuario="setor@teste.com",
        tipo_evento=f"tarefa_solicitacao_recusada_{solicitacao.id}",
    ).first()


def test_admin_consegue_recusar_solicitacao(client, login_as, op_com_setor):
    op, setor_origem = op_com_setor
    destino = criar_setor_destino(op)
    login_as("SETOR", setor_id=setor_origem.id)
    solicitar(client, op, destino)
    solicitacao = solicitacao_unica()

    login_as("ADMIN")
    resposta = client.post(f"/tarefas/solicitacoes/{solicitacao.id}/recusar")

    assert resposta.status_code == 302
    assert Tarefa.query.count() == 0


def test_tarefas_normais_continuam_funcionando(client, login_as, tarefa):
    login_as("SETOR", setor_id=tarefa.setor_id)

    resposta = client.post(f"/iniciar_tarefa/{tarefa.id}", headers={"Referer": f"/op/{tarefa.op_id}"})

    assert resposta.status_code == 302
    db.session.refresh(tarefa)
    assert tarefa.status == "EM ANDAMENTO"
