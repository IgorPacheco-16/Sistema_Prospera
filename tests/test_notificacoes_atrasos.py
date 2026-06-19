from datetime import timedelta

from database.models import db, Notificacao, OP, OPSetor, Setor, Tarefa
from tempo import hoje_brasilia


class ResultadoEmail:
    def __init__(self, enviado=True, erro=None):
        self.enviado = enviado
        self.erro = erro


def criar_tarefa_atrasada(setor):
    op = OP(
        nome="OP com atraso",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        prazo_final=hoje_brasilia() + timedelta(days=5),
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Tarefa vencida",
        prazo=hoje_brasilia() - timedelta(days=1),
        validado=False,
    )
    db.session.add(tarefa)
    db.session.commit()
    return op, tarefa


def criar_op_urgente(setor):
    op = OP(
        nome="OP urgente",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        prazo_final=hoje_brasilia() + timedelta(days=1),
        alta_prioridade=True,
    )
    db.session.add(op)
    db.session.flush()
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    db.session.commit()
    return op


def configurar_email_fake(monkeypatch, services, chamadas, resultado=None):
    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def enviar_email_fake(destinatarios, assunto, texto, html=None):
        chamadas.append({
            "destinatarios": destinatarios,
            "assunto": assunto,
            "texto": texto,
            "html": html,
        })
        return resultado or ResultadoEmail(enviado=True)

    monkeypatch.setattr(services, "enviar_email_smtp", enviar_email_fake)


def criar_notificacoes_atraso(tarefa, email_enviado=False):
    notificacoes = []
    for usuario in ["ATENDENTE", "PCP", "SETOR"]:
        notificacoes.append(Notificacao(
            usuario=usuario,
            mensagem="Tarefa atrasada",
            link=f"/op/{tarefa.op_id}?setor={tarefa.setor_id}&tarefa={tarefa.id}",
            op_id=tarefa.op_id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="tarefa_atrasada",
            email_enviado=email_enviado,
        ))
    db.session.add_all(notificacoes)
    db.session.commit()
    return notificacoes


def test_tarefa_nova_atrasada_cria_notificacao_e_envia_email_para_setor(app, setores, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    _, tarefa = criar_tarefa_atrasada(setores["Acabamento"])
    configurar_email_fake(monkeypatch, services, chamadas)

    resumo = services.verificar_atrasos()
    db.session.commit()

    notificacao_setor = Notificacao.query.filter_by(
        usuario="SETOR",
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_atrasada",
    ).first()
    assert resumo["notificacoes_criadas"] == 3
    assert notificacao_setor is not None
    assert notificacao_setor.email_enviado is True
    assert len(chamadas) == 1
    assert "setor@teste.com" in chamadas[0]["destinatarios"]


def test_tarefa_atrasada_com_notificacao_existente_sem_email_envia_uma_vez(app, setores, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    _, tarefa = criar_tarefa_atrasada(setores["Acabamento"])
    criar_notificacoes_atraso(tarefa, email_enviado=False)
    configurar_email_fake(monkeypatch, services, chamadas)

    resumo = services.verificar_atrasos()
    db.session.commit()

    notificacoes = Notificacao.query.filter_by(
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_atrasada",
    ).all()
    assert resumo["notificacoes_criadas"] == 0
    assert len(chamadas) == 1
    assert all(n.email_enviado for n in notificacoes)


def test_tarefa_atrasada_com_email_ja_enviado_nao_reenvia(app, setores, monkeypatch):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    _, tarefa = criar_tarefa_atrasada(setores["Acabamento"])
    criar_notificacoes_atraso(tarefa, email_enviado=True)
    configurar_email_fake(monkeypatch, services, chamadas)

    resumo = services.verificar_atrasos()
    db.session.commit()

    assert resumo["notificacoes_criadas"] == 0
    assert resumo["emails_tarefa_atrasada_enviados"] == 0
    assert chamadas == []


def test_tarefa_atrasada_setor_sem_usuarios_nao_quebra(app, monkeypatch, caplog):
    import app as app_module

    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = True
    services = app_module.notificacoes_module
    chamadas = []
    setor = Setor(nome="Setor sem usuarios")
    db.session.add(setor)
    db.session.commit()
    criar_tarefa_atrasada(setor)
    configurar_email_fake(monkeypatch, services, chamadas)
    caplog.set_level("WARNING")

    services.verificar_atrasos()
    db.session.commit()

    assert "email_operacional_setor_sem_usuarios_ativos" in caplog.text


def test_config_global_desliga_email_mesmo_com_enviar_emails_true(app, setores, monkeypatch, caplog):
    import app as app_module

    services = app_module.notificacoes_module
    _, tarefa = criar_tarefa_atrasada(setores["Acabamento"])
    app.config["EMAILS_OPERACIONAIS_ATIVOS"] = False
    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def falhar_se_enviar_email(*args, **kwargs):
        raise AssertionError("config global deve bloquear envio SMTP")

    monkeypatch.setattr(services, "enviar_email_smtp", falhar_se_enviar_email)
    caplog.set_level("INFO")

    resumo = services.verificar_atrasos(enviar_emails=True)
    db.session.commit()

    notificacoes = Notificacao.query.filter_by(
        tarefa_id=tarefa.id,
        tipo_evento="tarefa_atrasada",
    ).all()
    assert resumo["notificacoes_criadas"] == 3
    assert resumo["emails_tarefa_atrasada_enviados"] == 0
    assert len(notificacoes) == 3
    assert all(n.email_enviado is False for n in notificacoes)
    assert "email_operacional_desativado_por_configuracao evento=tarefa_atrasada" in caplog.text


def test_dashboard_nao_envia_email_sincrono_quando_smtp_falha(client, login_as, setores, monkeypatch):
    import app as app_module

    services = app_module.notificacoes_module
    chamadas = []
    criar_tarefa_atrasada(setores["Acabamento"])
    configurar_email_fake(
        monkeypatch,
        services,
        chamadas,
        resultado=ResultadoEmail(enviado=False, erro="Falha SMTP: RuntimeError"),
    )

    def falhar_se_enviar_email(*args, **kwargs):
        chamadas.append({"args": args, "kwargs": kwargs})
        raise AssertionError("dashboard nao deve enviar email sincrono")

    monkeypatch.setattr(services, "enviar_email_smtp", falhar_se_enviar_email)
    login_as("ADMIN")

    resposta = client.get("/dashboard")

    assert resposta.status_code == 200
    assert chamadas == []


def test_dashboard_cria_notificacao_op_urgente_sem_email_sincrono(client, login_as, setores, monkeypatch):
    import app as app_module

    services = app_module.notificacoes_module
    chamadas = []
    op = criar_op_urgente(setores["Acabamento"])

    monkeypatch.setattr(services, "smtp_configurado", lambda: True)

    def falhar_se_enviar_email(*args, **kwargs):
        chamadas.append({"args": args, "kwargs": kwargs})
        raise AssertionError("dashboard nao deve enviar email sincrono")

    monkeypatch.setattr(services, "enviar_email_smtp", falhar_se_enviar_email)
    login_as("ADMIN")

    resposta = client.get("/dashboard")

    notificacoes = Notificacao.query.filter_by(
        op_id=op.id,
        tipo_evento="op_urgente",
    ).all()
    usuarios = sorted(n.usuario for n in notificacoes)

    assert resposta.status_code == 200
    assert chamadas == []
    assert usuarios == ["ATENDENTE", "PCP", "SETOR"]
    assert all(n.email_enviado is False for n in notificacoes)


def test_gerar_notificacoes_pendentes_nao_comita_sem_alteracoes(app, monkeypatch):
    import app as app_module

    services = app_module.notificacoes_module
    commits = []
    monkeypatch.setattr(services.db.session, "commit", lambda: commits.append(True))

    assert services.gerar_notificacoes_pendentes(forcar=True, enviar_emails=False) is True
    assert commits == []
