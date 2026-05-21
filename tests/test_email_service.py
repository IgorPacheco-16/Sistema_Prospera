import logging

import email_service


EMAIL_ENV_KEYS = [
    "MAIL_SERVER",
    "MAIL_PORT",
    "MAIL_USERNAME",
    "MAIL_PASSWORD",
    "MAIL_DEFAULT_SENDER",
    "MAIL_USE_TLS",
    "MAIL_USE_SSL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_USER",
    "EMAIL_USERNAME",
    "EMAIL_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_USE_TLS",
    "EMAIL_USE_SSL",
]


def limpar_env_email(monkeypatch):
    for chave in EMAIL_ENV_KEYS:
        monkeypatch.delenv(chave, raising=False)


def configurar_env_email(monkeypatch):
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_PORT", "587")
    monkeypatch.setenv("MAIL_USERNAME", "usuario@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "senha-secreta")
    monkeypatch.setenv("MAIL_DEFAULT_SENDER", "sistema@example.com")
    monkeypatch.setenv("MAIL_USE_TLS", "true")
    monkeypatch.setenv("MAIL_USE_SSL", "false")


def test_configuracao_ausente_retorna_erro_claro(monkeypatch, caplog):
    limpar_env_email(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    with caplog.at_level(logging.ERROR):
        resultado = email_service.enviar_email(
            ["destino@example.com"],
            "Assunto",
            "Texto",
        )

    assert resultado.enviado is False
    assert "Configuracao SMTP ausente ou invalida" in resultado.erro
    assert "MAIL_SERVER" in resultado.erro
    assert "MAIL_PASSWORD" in resultado.erro
    assert "email_nao_enviado motivo=configuracao_ausente" in caplog.text
    assert "senha-secreta" not in caplog.text


def test_erro_smtp_e_logado_sem_expor_segredos(monkeypatch, caplog):
    configurar_env_email(monkeypatch)

    class SMTPFalho:
        def __init__(self, server, port):
            self.server = server
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            pass

        def login(self, username, password):
            raise RuntimeError("erro fake com senha-secreta")

        def send_message(self, mensagem):
            raise AssertionError("nao deveria enviar")

    monkeypatch.setattr(email_service.smtplib, "SMTP", SMTPFalho)

    with caplog.at_level(logging.ERROR):
        resultado = email_service.enviar_email(
            ["destino@example.com"],
            "Assunto",
            "Texto",
        )

    assert resultado.enviado is False
    assert resultado.erro == "Falha SMTP: RuntimeError"
    assert "email_nao_enviado motivo=erro_smtp tipo=RuntimeError" in caplog.text
    assert "senha-secreta" not in caplog.text
