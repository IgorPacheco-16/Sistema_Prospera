import pytest
from flask import Flask


def test_database_url_production_exige_valor(monkeypatch):
    import app as app_module

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL obrigatoria"):
        app_module.config_module.database_url_para_ambiente("production")


def test_database_url_production_rejeita_sqlite(monkeypatch):
    import app as app_module

    monkeypatch.setenv("DATABASE_URL", "sqlite:///database.db")

    with pytest.raises(RuntimeError, match="Use PostgreSQL"):
        app_module.config_module.database_url_para_ambiente("production")


def test_database_url_production_exige_nome_do_banco(monkeypatch):
    import app as app_module

    monkeypatch.setenv("DATABASE_URL", "postgresql://usuario:senha@localhost")

    with pytest.raises(RuntimeError, match="nome do banco"):
        app_module.config_module.database_url_para_ambiente("production")


def test_database_url_production_converte_postgres(monkeypatch):
    import app as app_module

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://usuario:senha@localhost:5432/pacheco"
    )

    assert (
        app_module.config_module.database_url_para_ambiente("production")
        == "postgresql://usuario:senha@localhost:5432/pacheco"
    )


def test_database_url_test_mantem_sqlite_de_teste(monkeypatch):
    import app as app_module

    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert app_module.config_module.database_url_para_ambiente("test") == "sqlite:///:memory:"


def test_configure_app_production_sem_database_url_falha_com_mensagem_objetiva(monkeypatch):
    import app as app_module

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL obrigatoria"):
        app_module.config_module.configure_app(Flask(__name__))


def test_configure_app_carrega_variaveis_mail_no_app_config(monkeypatch):
    import app as app_module

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_PORT", "465")
    monkeypatch.setenv("MAIL_USERNAME", "usuario@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "senha")
    monkeypatch.setenv("MAIL_DEFAULT_SENDER", "sistema@example.com")
    monkeypatch.setenv("MAIL_ENABLED", "true")
    monkeypatch.setenv("MAIL_USE_SSL", "true")

    flask_app = Flask(__name__)
    app_module.config_module.configure_app(flask_app)

    assert flask_app.config["MAIL_SERVER"] == "smtp.example.com"
    assert flask_app.config["MAIL_PORT"] == "465"
    assert flask_app.config["MAIL_ENABLED"] == "true"
    assert flask_app.config["MAIL_USE_SSL"] == "true"


def test_configure_app_desativa_emails_operacionais_por_padrao(monkeypatch):
    import app as app_module

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("EMAILS_OPERACIONAIS_ATIVOS", raising=False)
    monkeypatch.delenv("ENVIAR_EMAILS_OPERACIONAIS", raising=False)

    flask_app = Flask(__name__)
    app_module.config_module.configure_app(flask_app)

    assert flask_app.config["EMAILS_OPERACIONAIS_ATIVOS"] is False


def test_configure_app_permite_reativar_emails_operacionais_por_env(monkeypatch):
    import app as app_module

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ENVIAR_EMAILS_OPERACIONAIS", "true")

    flask_app = Flask(__name__)
    app_module.config_module.configure_app(flask_app)

    assert flask_app.config["EMAILS_OPERACIONAIS_ATIVOS"] is True
