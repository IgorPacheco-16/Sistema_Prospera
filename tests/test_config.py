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
