from datetime import timedelta

from database.models import db, NotificationEmailDelivery, OP, OPSetor, Setor, Tarefa, User
from tempo import hoje_brasilia


class ResultadoEmail:
    enviado = True
    erro = None


def configurar_email_real_fake(app, monkeypatch, relatorio_module, chamadas):
    app.config.update(
        MAIL_ENABLED="true",
        MAIL_SERVER="smtp.example.com",
        MAIL_PORT="587",
        MAIL_USERNAME="usuario@example.com",
        MAIL_PASSWORD="senha-secreta",
        MAIL_DEFAULT_SENDER="sistema@example.com",
        MAIL_USE_TLS="true",
        MAIL_USE_SSL="false",
        EMAILS_OPERACIONAIS_ATIVOS=True,
    )

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas.append({
            "destinatarios": destinatarios,
            "assunto": assunto,
            "texto": texto,
            "html": html,
        })
        return ResultadoEmail()

    monkeypatch.setattr(relatorio_module, "enviar_email", enviar_email_fake)


def criar_usuario(email, tipo="SETOR", setor=None, nome=None, ativo=True):
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


def criar_op(setor, nome="OP Relatorio", atendente="atendente@teste.com", prazo=None, alta=False):
    op = OP(
        nome=nome,
        cliente="Cliente X",
        status="EM ANDAMENTO",
        atendente=atendente,
        prazo_final=prazo,
        alta_prioridade=alta,
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    db.session.commit()
    return op


def criar_tarefa(op, setor, nome="Tarefa Relatorio", prazo=None, entregue=False):
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome=nome,
        prazo=prazo,
        status="EM VALIDAÇÃO" if entregue else "PENDENTE",
        entregue=entregue,
        validado=False,
    )
    db.session.add(tarefa)
    db.session.commit()
    return tarefa


def tarefas_da_secao(relatorio, secao):
    return [item.texto for item in relatorio.secoes[secao]]


def destinatarios(chamadas):
    return [chamada["destinatarios"][0] for chamada in chamadas]


def test_relatorio_individual_para_usuarios_do_mesmo_setor_sem_email_coletivo(app, setores, monkeypatch):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    chamadas = []
    configurar_email_real_fake(app, monkeypatch, relatorio_module, chamadas)
    setor = setores["Acabamento"]
    User.query.filter_by(email="setor@teste.com").update({"nome": "Joao Setor"})
    User.query.filter_by(email="pcp@teste.com").update({"nome": "PCP Um"})
    db.session.commit()
    maria = criar_usuario("maria.setor@teste.com", setor=setor, nome="Maria Setor")
    op = criar_op(setor, atendente="outro@teste.com")
    criar_tarefa(op, setor, prazo=hoje_brasilia() - timedelta(days=1))

    relatorio_module.enviar_relatorios_operacionais("10h")

    enviados = destinatarios(chamadas)
    assert "setor@teste.com" in enviados
    assert "maria.setor@teste.com" in enviados
    assert all(len(chamada["destinatarios"]) == 1 for chamada in chamadas)
    for chamada in chamadas:
        destinatario = chamada["destinatarios"][0]
        outros = [email for email in enviados if email != destinatario]
        assert not any(email in chamada["texto"] for email in outros)
    assert maria.email in enviados


def test_tarefa_sem_responsavel_aparece_para_todos_usuarios_ativos_do_setor(app, setores):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    setor = setores["Acabamento"]
    joao = User.query.filter_by(email="setor@teste.com").first()
    maria = criar_usuario("maria.sem.responsavel@teste.com", setor=setor)
    op = criar_op(setor, atendente="outro@teste.com")
    criar_tarefa(op, setor, nome="Tarefa geral atrasada", prazo=hoje_brasilia() - timedelta(days=1))

    relatorio_joao = relatorio_module.montar_relatorio_usuario(joao, "10h")
    relatorio_maria = relatorio_module.montar_relatorio_usuario(maria, "10h")

    assert "Tarefa geral atrasada" in "\n".join(tarefas_da_secao(relatorio_joao, "tarefas_atrasadas"))
    assert "Tarefa geral atrasada" in "\n".join(tarefas_da_secao(relatorio_maria, "tarefas_atrasadas"))


def test_tarefa_com_responsavel_aparece_apenas_para_responsavel(app, setores):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    setor = setores["Acabamento"]
    responsavel = criar_usuario("responsavel.relatorio@teste.com", setor=setor)
    colega = criar_usuario("colega.relatorio@teste.com", setor=setor)
    op = criar_op(setor, atendente="outro@teste.com")
    tarefa = criar_tarefa(
        op,
        setor,
        nome="Tarefa somente responsavel",
        prazo=hoje_brasilia() - timedelta(days=1),
    )
    tarefa.responsaveis = [responsavel]
    db.session.commit()

    relatorio_responsavel = relatorio_module.montar_relatorio_usuario(responsavel, "10h")
    relatorio_colega = relatorio_module.montar_relatorio_usuario(colega, "10h")

    assert "Tarefa somente responsavel" in "\n".join(tarefas_da_secao(relatorio_responsavel, "tarefas_atrasadas"))
    assert tarefas_da_secao(relatorio_colega, "tarefas_atrasadas") == []


def test_usuario_setor_nao_recebe_tarefa_de_outro_setor(app, setores):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    acabamento = setores["Acabamento"]
    impressao = Setor(nome="Impressao")
    db.session.add(impressao)
    db.session.commit()
    usuario_acabamento = User.query.filter_by(email="setor@teste.com").first()
    op = criar_op(impressao, atendente="outro@teste.com")
    criar_tarefa(op, impressao, nome="Tarefa de outro setor", prazo=hoje_brasilia() - timedelta(days=1))

    relatorio = relatorio_module.montar_relatorio_usuario(usuario_acabamento, "10h")

    texto = "\n".join(tarefas_da_secao(relatorio, "tarefas_atrasadas"))
    assert "Tarefa de outro setor" not in texto
    assert usuario_acabamento.setor_id == acabamento.id


def test_pcp_recebe_relatorio_individual_com_visao_ampla(app, setores, monkeypatch):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    chamadas = []
    configurar_email_real_fake(app, monkeypatch, relatorio_module, chamadas)
    criar_usuario("pcp.dois@teste.com", tipo="PCP")
    setor = setores["Acabamento"]
    op = criar_op(setor, atendente="outro@teste.com", alta=True)
    criar_tarefa(op, setor, prazo=hoje_brasilia() - timedelta(days=1))

    relatorio_module.enviar_relatorios_operacionais("10h")

    enviados = destinatarios(chamadas)
    assert "pcp@teste.com" in enviados
    assert "pcp.dois@teste.com" in enviados
    assert all(len(chamada["destinatarios"]) == 1 for chamada in chamadas)


def test_atendente_recebe_ops_relacionadas_a_ele(app, setores):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    setor = setores["Acabamento"]
    atendente = User.query.filter_by(email="atendente@teste.com").first()
    op_dele = criar_op(
        setor,
        nome="OP do atendente",
        atendente=atendente.email,
        prazo=hoje_brasilia() - timedelta(days=1),
    )
    criar_op(
        setor,
        nome="OP de outro atendente",
        atendente="outro@teste.com",
        prazo=hoje_brasilia() - timedelta(days=1),
    )

    relatorio = relatorio_module.montar_relatorio_usuario(atendente, "10h")
    texto = "\n".join(item.texto for item in relatorio.secoes["ops_atrasadas"])

    assert str(op_dele.id) in texto
    assert "OP de outro atendente" not in texto


def test_espectador_nao_recebe_relatorio(app):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    relatorios = relatorio_module.montar_relatorios("10h")

    assert all(relatorio.usuario.tipo != "ESPECTADOR" for relatorio in relatorios)


def test_flags_bloqueiam_envio_real_e_registram_pulo(app, setores, monkeypatch):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    setor = setores["Acabamento"]
    op = criar_op(setor, atendente="outro@teste.com")
    criar_tarefa(op, setor, prazo=hoje_brasilia() - timedelta(days=1))

    def falhar_se_enviar(*args, **kwargs):
        raise AssertionError("nao deve enviar SMTP real")

    monkeypatch.setattr(relatorio_module, "enviar_email", falhar_se_enviar)
    app.config.update(MAIL_ENABLED="false", EMAILS_OPERACIONAIS_ATIVOS=True)

    resumo = relatorio_module.enviar_relatorios_operacionais("10h")

    assert resumo["enviados"] == 0
    assert NotificationEmailDelivery.query.filter_by(status="pulou").count() > 0
    assert NotificationEmailDelivery.query.filter(
        NotificationEmailDelivery.erro == "MAIL_ENABLED=false"
    ).count() > 0

    db.session.query(NotificationEmailDelivery).delete()
    db.session.commit()
    app.config.update(
        MAIL_ENABLED="true",
        MAIL_SERVER="smtp.example.com",
        MAIL_PORT="587",
        MAIL_USERNAME="usuario@example.com",
        MAIL_PASSWORD="senha-secreta",
        MAIL_DEFAULT_SENDER="sistema@example.com",
        EMAILS_OPERACIONAIS_ATIVOS=False,
    )

    resumo = relatorio_module.enviar_relatorios_operacionais("15h")

    assert resumo["enviados"] == 0
    assert NotificationEmailDelivery.query.filter(
        NotificationEmailDelivery.erro == "EMAILS_OPERACIONAIS_ATIVOS=false"
    ).count() > 0


def test_nao_duplica_relatorio_mesma_janela_e_data(app, setores, monkeypatch):
    import app as app_module

    relatorio_module = app_module.relatorio_module
    chamadas = []
    configurar_email_real_fake(app, monkeypatch, relatorio_module, chamadas)
    setor = setores["Acabamento"]
    op = criar_op(setor, atendente="outro@teste.com")
    criar_tarefa(op, setor, prazo=hoje_brasilia() - timedelta(days=1))

    relatorio_module.enviar_relatorios_operacionais("10h")
    relatorio_module.enviar_relatorios_operacionais("10h")

    enviados_setor = [
        chamada for chamada in chamadas
        if chamada["destinatarios"] == ["setor@teste.com"]
    ]
    assert len(enviados_setor) == 1
    assert NotificationEmailDelivery.query.filter_by(
        recipient_email="setor@teste.com",
        janela="10h",
        status="enviado",
    ).count() == 1
    assert NotificationEmailDelivery.query.filter_by(
        recipient_email="setor@teste.com",
        janela="10h",
        status="pulou",
        erro="duplicado",
    ).count() == 1


def test_comando_aceita_janelas_validas_e_recusa_invalida(app):
    runner = app.test_cli_runner()

    resultado_10h = runner.invoke(args=["enviar-relatorio-operacional", "--janela", "10h"])
    resultado_15h = runner.invoke(args=["enviar-relatorio-operacional", "--janela", "15h"])
    resultado_invalido = runner.invoke(args=["enviar-relatorio-operacional", "--janela", "12h"])

    assert resultado_10h.exit_code == 0
    assert "Janela: 10h" in resultado_10h.output
    assert resultado_15h.exit_code == 0
    assert "Janela: 15h" in resultado_15h.output
    assert resultado_invalido.exit_code != 0
    assert "Janela invalida. Use 10h ou 15h." in resultado_invalido.output
