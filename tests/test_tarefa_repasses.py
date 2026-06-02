from database.models import db, HistoricoOP, Notificacao, TarefaResponsavel, User
from metricas_responsaveis import ranking_metricas_responsaveis


def criar_usuario(email, setor, nome=None, tipo="SETOR", ativo=True):
    usuario = User(
        nome=nome or email,
        email=email,
        senha="123",
        tipo=tipo,
        setor_id=setor.id,
        ativo=ativo,
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def atribuir(tarefa, usuarios):
    tarefa.responsaveis = usuarios
    db.session.commit()
    return usuarios


def emails_responsaveis(tarefa):
    db.session.refresh(tarefa)
    return sorted(usuario.email for usuario in tarefa.responsaveis)


def proposta_repasse(client, tarefa, entram, saem, observacao=""):
    return client.post(
        f"/tarefas/{tarefa.id}/responsaveis",
        data={
            "usuario_ids": [str(usuario.id) for usuario in entram],
            "sair_ids": [str(usuario.id) for usuario in saem],
            "tipo": "REPASSE",
            "observacao": observacao,
        },
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )


def inclusao(client, tarefa, usuarios, observacao=""):
    return client.post(
        f"/tarefas/{tarefa.id}/responsaveis",
        data={
            "usuario_ids": [str(usuario.id) for usuario in usuarios],
            "tipo": "INCLUSAO",
            "observacao": observacao,
        },
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )


def vinculo(tarefa, usuario, papel=None, tipo="REPASSE"):
    query = TarefaResponsavel.query.filter_by(
        tarefa_id=tarefa.id,
        usuario_id=usuario.id,
        tipo=tipo,
    )
    if papel:
        query = query.filter_by(repasse_papel=papel)
    return query.order_by(TarefaResponsavel.id.desc()).first()


def aceitar(client, login_as, tarefa, usuario, papel=None, tipo="REPASSE"):
    item = vinculo(tarefa, usuario, papel=papel, tipo=tipo)
    login_as("SETOR", email=usuario.email, setor_id=tarefa.setor_id)
    resposta = client.post(
        f"/tarefas/responsaveis/{item.id}/aceitar",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    db.session.refresh(item)
    db.session.refresh(tarefa)
    return resposta, item


def recusar(client, login_as, tarefa, usuario, papel=None, tipo="REPASSE"):
    item = vinculo(tarefa, usuario, papel=papel, tipo=tipo)
    login_as("SETOR", email=usuario.email, setor_id=tarefa.setor_id)
    resposta = client.post(
        f"/tarefas/responsaveis/{item.id}/recusar",
        headers={"Referer": f"/op/{tarefa.op_id}"},
    )
    db.session.refresh(item)
    db.session.refresh(tarefa)
    return resposta, item


def criar_quatro_responsaveis(tarefa):
    usuarios = [
        criar_usuario(f"atual.{indice}@teste.com", tarefa.setor, f"Atual {indice}")
        for indice in range(4)
    ]
    atribuir(tarefa, usuarios)
    return usuarios


def test_repasse_cria_proposta_pendente_sem_alterar_responsaveis_atuais(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("diana.repasse@teste.com", tarefa.setor, "Diana Repasse")
    eduardo = criar_usuario("eduardo.repasse@teste.com", tarefa.setor, "Eduardo Repasse")
    fernanda = criar_usuario("fernanda.repasse@teste.com", tarefa.setor, "Fernanda Repasse")
    login_as("SETOR", email=igor.email, setor_id=tarefa.setor_id)

    resposta = proposta_repasse(client, tarefa, [diana, eduardo, fernanda], [ana, bruno, igor])

    assert resposta.status_code == 302
    assert emails_responsaveis(tarefa) == sorted([ana.email, bruno.email, carlos.email, igor.email])
    lote = TarefaResponsavel.query.filter_by(tarefa_id=tarefa.id, tipo="REPASSE").all()
    assert len(lote) == 6
    assert {item.status for item in lote} == {"PENDENTE"}
    assert {item.repasse_status for item in lote} == {"PENDENTE"}
    assert {item.repasse_lote_id for item in lote}
    assert Notificacao.query.filter_by(tarefa_id=tarefa.id).count() == 6
    assert HistoricoOP.query.filter_by(op_id=tarefa.op_id, acao="Repasse proposto").first()


def test_usuarios_de_entrada_aceitam_mas_nao_entram_ate_todos_aceitarem(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("entrada.diana@teste.com", tarefa.setor, "Entrada Diana")
    eduardo = criar_usuario("entrada.eduardo@teste.com", tarefa.setor, "Entrada Eduardo")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana, eduardo], [ana, bruno])

    resposta, vinculo_diana = aceitar(client, login_as, tarefa, diana, papel="ENTRADA")
    aceitar(client, login_as, tarefa, eduardo, papel="ENTRADA")

    assert resposta.status_code == 302
    assert vinculo_diana.status == "APROVADO"
    assert emails_responsaveis(tarefa) == sorted([ana.email, bruno.email, carlos.email, igor.email])


def test_usuarios_de_saida_aceitam_mas_nao_saem_ate_todos_aceitarem(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("saida.diana@teste.com", tarefa.setor, "Saida Diana")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana], [ana, bruno])

    resposta, vinculo_ana = aceitar(client, login_as, tarefa, ana, papel="SAIDA")
    aceitar(client, login_as, tarefa, bruno, papel="SAIDA")

    assert resposta.status_code == 302
    assert vinculo_ana.status == "APROVADO"
    assert emails_responsaveis(tarefa) == sorted([ana.email, bruno.email, carlos.email, igor.email])


def test_quando_todos_aceitam_repasse_aplica_troca_de_uma_vez(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("final.diana@teste.com", tarefa.setor, "Final Diana")
    eduardo = criar_usuario("final.eduardo@teste.com", tarefa.setor, "Final Eduardo")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana, eduardo], [ana, igor])

    aceitar(client, login_as, tarefa, diana, papel="ENTRADA")
    aceitar(client, login_as, tarefa, ana, papel="SAIDA")
    aceitar(client, login_as, tarefa, eduardo, papel="ENTRADA")
    resposta, vinculo_igor = aceitar(client, login_as, tarefa, igor, papel="SAIDA")

    assert resposta.status_code == 302
    assert emails_responsaveis(tarefa) == sorted([bruno.email, carlos.email, diana.email, eduardo.email])
    lote = TarefaResponsavel.query.filter_by(repasse_lote_id=vinculo_igor.repasse_lote_id).all()
    assert {item.repasse_status for item in lote} == {"CONCLUIDO"}
    assert HistoricoOP.query.filter_by(op_id=tarefa.op_id, acao="Repasse concluido").first()


def test_se_alguem_de_entrada_recusar_repasse_cancela_sem_mudar_responsaveis(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("recusa.entrada.diana@teste.com", tarefa.setor, "Recusa Entrada")
    eduardo = criar_usuario("recusa.entrada.eduardo@teste.com", tarefa.setor, "Recusa Entrada Eduardo")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana, eduardo], [ana, bruno])

    aceitar(client, login_as, tarefa, ana, papel="SAIDA")
    resposta, vinculo_diana = recusar(client, login_as, tarefa, diana, papel="ENTRADA")

    assert resposta.status_code == 302
    assert emails_responsaveis(tarefa) == sorted([ana.email, bruno.email, carlos.email, igor.email])
    lote = TarefaResponsavel.query.filter_by(repasse_lote_id=vinculo_diana.repasse_lote_id).all()
    assert {item.repasse_status for item in lote} == {"RECUSADO"}
    assert {item.status for item in lote} == {"RECUSADO", "CANCELADO"}
    assert Notificacao.query.filter_by(tarefa_id=tarefa.id, usuario="pcp@teste.com").first()


def test_se_alguem_de_saida_recusar_repasse_cancela_sem_mudar_responsaveis(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("recusa.saida.diana@teste.com", tarefa.setor, "Recusa Saida")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana], [ana, bruno])

    aceitar(client, login_as, tarefa, diana, papel="ENTRADA")
    resposta, vinculo_bruno = recusar(client, login_as, tarefa, bruno, papel="SAIDA")

    assert resposta.status_code == 302
    assert emails_responsaveis(tarefa) == sorted([ana.email, bruno.email, carlos.email, igor.email])
    lote = TarefaResponsavel.query.filter_by(repasse_lote_id=vinculo_bruno.repasse_lote_id).all()
    assert {item.repasse_status for item in lote} == {"RECUSADO"}
    assert vinculo_bruno.status == "RECUSADO"


def test_solicitante_selecionado_para_sair_so_sai_no_final(client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("solicitante.diana@teste.com", tarefa.setor, "Solicitante Diana")
    login_as("SETOR", email=igor.email, setor_id=tarefa.setor_id)
    proposta_repasse(client, tarefa, [diana], [igor])

    aceitar(client, login_as, tarefa, diana, papel="ENTRADA")
    assert igor.email in emails_responsaveis(tarefa)

    aceitar(client, login_as, tarefa, igor, papel="SAIDA")
    assert emails_responsaveis(tarefa) == sorted([ana.email, bruno.email, carlos.email, diana.email])


def test_limite_de_quatro_e_validado_antes_de_criar_proposta(client, login_as, tarefa):
    atuais = criar_quatro_responsaveis(tarefa)
    novos = [
        criar_usuario(f"limite.repasse.{indice}@teste.com", tarefa.setor, f"Limite {indice}")
        for indice in range(2)
    ]
    login_as("ADMIN")

    resposta = proposta_repasse(client, tarefa, novos, [atuais[0]])

    assert resposta.status_code == 400
    assert "limite de 4 responsaveis" in resposta.get_data(as_text=True)
    assert TarefaResponsavel.query.filter_by(tarefa_id=tarefa.id, tipo="REPASSE").count() == 0


def test_metricas_nao_mudam_enquanto_repasse_esta_pendente(app, client, login_as, tarefa):
    ana, bruno, _carlos, _igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("metrica.pendente.diana@teste.com", tarefa.setor, "Metrica Pendente")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana], [ana])
    aceitar(client, login_as, tarefa, diana, papel="ENTRADA")

    ranking = ranking_metricas_responsaveis([tarefa], tarefa.criada_em.date())["usuarios"]

    assert sorted(linha["nome"] for linha in ranking) == sorted([
        "Atual 0",
        "Atual 1",
        "Atual 2",
        "Atual 3",
    ])
    assert bruno.email in emails_responsaveis(tarefa)


def test_metricas_mudam_apenas_apos_repasse_concluido(app, client, login_as, tarefa):
    ana, bruno, carlos, igor = criar_quatro_responsaveis(tarefa)
    diana = criar_usuario("metrica.final.diana@teste.com", tarefa.setor, "Metrica Final")
    login_as("PCP")
    proposta_repasse(client, tarefa, [diana], [ana])

    aceitar(client, login_as, tarefa, diana, papel="ENTRADA")
    aceitar(client, login_as, tarefa, ana, papel="SAIDA")
    ranking = ranking_metricas_responsaveis([tarefa], tarefa.criada_em.date())["usuarios"]

    assert sorted(linha["nome"] for linha in ranking) == sorted([
        bruno.nome,
        carlos.nome,
        igor.nome,
        diana.nome,
    ])


def test_inclusao_continua_individual_e_parcial(client, login_as, tarefa):
    ana = criar_usuario("inclusao.ana@teste.com", tarefa.setor, "Inclusao Ana")
    bia = criar_usuario("inclusao.bia@teste.com", tarefa.setor, "Inclusao Bia")
    login_as("ADMIN")
    resposta = inclusao(client, tarefa, [ana, bia])

    assert resposta.status_code == 302
    aceitar(client, login_as, tarefa, ana, tipo="INCLUSAO")

    assert emails_responsaveis(tarefa) == [ana.email]
    assert vinculo(tarefa, bia, tipo="INCLUSAO").status == "PENDENTE"


def test_repassar_bloqueia_usuario_duplicado(client, login_as, tarefa):
    destino = criar_usuario("duplicado.repasse@teste.com", tarefa.setor, "Duplicado Repasse")
    atual = criar_usuario("atual.duplicado.repasse@teste.com", tarefa.setor, "Atual Duplicado")
    atribuir(tarefa, [destino, atual])
    login_as("ADMIN")

    resposta = proposta_repasse(client, tarefa, [destino], [atual])

    assert resposta.status_code == 400
    assert "ja esta vinculado" in resposta.get_data(as_text=True)


def test_usuario_sem_permissao_nao_consegue_repassar(client, login_as, tarefa):
    atual = criar_usuario("atual.sem.permissao@teste.com", tarefa.setor, "Atual Sem Permissao")
    destino = criar_usuario("destino.sem.permissao@teste.com", tarefa.setor, "Destino Sem Permissao")
    atribuir(tarefa, [atual])
    login_as("ATENDENTE")

    resposta = proposta_repasse(client, tarefa, [destino], [atual])

    assert resposta.status_code == 403
    assert TarefaResponsavel.query.filter_by(tarefa_id=tarefa.id, usuario_id=destino.id).first() is None


def test_setor_nao_consegue_repassar_tarefa_de_outro_setor(client, login_as, tarefa, setores):
    atual = criar_usuario("atual.outro.setor@teste.com", tarefa.setor, "Atual Outro Setor")
    destino = criar_usuario("destino.outro.setor@teste.com", tarefa.setor, "Destino Outro Setor")
    atribuir(tarefa, [atual])
    login_as("SETOR", setor_id=setores["PCP"].id)

    resposta = proposta_repasse(client, tarefa, [destino], [atual])

    assert resposta.status_code == 403
    assert TarefaResponsavel.query.filter_by(tarefa_id=tarefa.id, usuario_id=destino.id, tipo="REPASSE").first() is None


def test_repassar_nao_permite_usuario_inativo(client, login_as, tarefa):
    atual = criar_usuario("atual.inativo.repasse@teste.com", tarefa.setor, "Atual Inativo")
    destino = criar_usuario("inativo.repasse@teste.com", tarefa.setor, "Inativo Repasse", ativo=False)
    atribuir(tarefa, [atual])
    login_as("ADMIN")

    resposta = proposta_repasse(client, tarefa, [destino], [atual])

    assert resposta.status_code == 400
    assert "inativo" in resposta.get_data(as_text=True)


def test_detalhe_op_renderiza_campos_da_proposta_de_repasse(client, login_as, tarefa):
    atual = criar_usuario("picker.atual@teste.com", tarefa.setor, "Picker Atual")
    destino = criar_usuario("picker.destino@teste.com", tarefa.setor, "Picker Destino")
    atribuir(tarefa, [atual])
    login_as("ADMIN")

    html = client.get(f"/op/{tarefa.op_id}").get_data(as_text=True)

    assert f'id="responsaveisRepasse{tarefa.id}"' in html
    assert f'id="responsaveisSaida{tarefa.id}"' in html
    assert 'name="usuario_ids"' in html
    assert 'name="sair_ids"' in html
    assert "Quem vai entrar" in html
    assert "Quem vai sair" in html
    assert "O repasse s&oacute; ser&aacute; conclu&iacute;do" in html
    assert f'value="{destino.id}"' in html
    assert f'value="{atual.id}"' in html


def test_metricas_gerais_nao_duplicam_tarefa_com_multiplos_responsaveis(client, login_as, tarefa):
    ana = criar_usuario("ana.geral.repasse@teste.com", tarefa.setor, "Ana Geral")
    bia = criar_usuario("bia.geral.repasse@teste.com", tarefa.setor, "Bia Geral")
    tarefa.responsaveis = [ana, bia]
    db.session.commit()
    login_as("ADMIN")

    html = client.get("/metricas").get_data(as_text=True)
    total_kpi = html[html.index('data-metricas-kpi="total"'):html.index('data-metricas-kpi="pendentes"')]

    assert "<strong>1</strong>" in total_kpi
