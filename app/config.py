import os
import secrets
from datetime import timedelta

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from database.models import db, Setor, User
from email_service import carregar_config_email
from tempo import agora_brasilia


AMBIENTES_COM_SEED_TESTE = {"development", "test"}


def app_env():
    return os.environ.get("APP_ENV", "production").strip().lower() or "production"


def database_url_para_ambiente(ambiente):
    database_url = (os.environ.get("DATABASE_URL") or "").strip()

    if ambiente == "test":
        return database_url or "sqlite:///:memory:"

    if ambiente == "development":
        return database_url or "sqlite:///database.db"

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL obrigatoria em production. "
            "Configure uma URL PostgreSQL valida."
        )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    try:
        url = make_url(database_url)
    except ArgumentError as erro:
        raise RuntimeError(
            "DATABASE_URL invalida em production. "
            "Configure uma URL PostgreSQL valida."
        ) from erro

    if url.drivername.split("+", 1)[0] != "postgresql":
        raise RuntimeError(
            "DATABASE_URL invalida em production. "
            "Use PostgreSQL, por exemplo postgresql://usuario:senha@host/banco."
        )

    if not url.database:
        raise RuntimeError(
            "DATABASE_URL invalida em production. "
            "Informe o nome do banco PostgreSQL na URL."
        )

    return database_url


def configure_app(app):
    ambiente = app_env()
    database_url = database_url_para_ambiente(ambiente)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if ambiente == "development":
            secret_key = secrets.token_hex(32)
        else:
            raise RuntimeError(
                "SECRET_KEY obrigatoria em producao. "
                "Defina a variavel de ambiente SECRET_KEY."
            )

    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = (
        timedelta(hours=12) if ambiente == "production" else 0
    )
    carregar_config_email(app)


def adicionar_coluna_se_nao_existir(tabela, coluna, definicao):
    colunas = db.session.execute(text(f"PRAGMA table_info({tabela})")).fetchall()
    nomes_colunas = [item[1] for item in colunas]

    if coluna in nomes_colunas:
        return

    try:
        db.session.execute(text(
            f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"
        ))
        db.session.commit()
    except OperationalError as erro:
        db.session.rollback()
        if "duplicate column name" not in str(erro).lower():
            raise


def garantir_coluna_alta_prioridade():
    adicionar_coluna_se_nao_existir(
        "ops",
        "alta_prioridade",
        "BOOLEAN NOT NULL DEFAULT 0"
    )


def garantir_coluna_cliente_op():
    adicionar_coluna_se_nao_existir("ops", "cliente", "VARCHAR(200)")


def garantir_colunas_usuario():
    adicionar_coluna_se_nao_existir("users", "nome", "VARCHAR(100)")


def garantir_colunas_notificacao():
    adicionar_coluna_se_nao_existir("notificacoes", "link", "VARCHAR(255)")
    adicionar_coluna_se_nao_existir("notificacoes", "op_id", "INTEGER")
    adicionar_coluna_se_nao_existir("notificacoes", "tarefa_id", "INTEGER")
    adicionar_coluna_se_nao_existir("notificacoes", "setor_id", "INTEGER")
    adicionar_coluna_se_nao_existir("notificacoes", "tipo_evento", "VARCHAR(80)")


def garantir_colunas_tarefa():
    adicionar_coluna_se_nao_existir(
        "tarefas",
        "status",
        "VARCHAR(30) NOT NULL DEFAULT 'PENDENTE'"
    )
    adicionar_coluna_se_nao_existir("tarefas", "criada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "iniciada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "enviada_validacao_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "validada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "recusada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "entregue_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "concluida_em", "DATETIME")
    adicionar_coluna_se_nao_existir("tarefas", "motivo_recusa", "VARCHAR(255)")
    agora = agora_brasilia()
    db.session.execute(
        text("UPDATE tarefas SET criada_em = :agora WHERE criada_em IS NULL"),
        {"agora": agora}
    )
    db.session.execute(text(
        "UPDATE tarefas SET status = 'ENTREGUE' WHERE validado = 1"
    ))
    db.session.execute(text(
        "UPDATE tarefas "
        "SET status = 'EM VALIDA\u00c7\u00c3O' "
        "WHERE validado = 0 AND entregue = 1"
    ))
    db.session.execute(text(
        "UPDATE tarefas "
        "SET status = 'PENDENTE' "
        "WHERE status IS NULL OR status = ''"
    ))
    db.session.commit()


def garantir_colunas_op_metricas():
    adicionar_coluna_se_nao_existir("ops", "criada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("ops", "finalizada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("ops", "arquivada_em", "DATETIME")
    adicionar_coluna_se_nao_existir("ops", "caminho_pasta", "VARCHAR(500)")
    agora = agora_brasilia()
    db.session.execute(
        text("UPDATE ops SET criada_em = :agora WHERE criada_em IS NULL"),
        {"agora": agora}
    )
    db.session.commit()


def ambiente_permite_seed_teste(app):
    return app_env() in AMBIENTES_COM_SEED_TESTE


def criar_setores_padrao():
    setores_nomes = [
        "Atendimento",
        "Cria\u00e7\u00e3o",
        "Projeto",
        "Compras/Estoque",
        "PCP",
        "Arte Final",
        "Pr\u00e9-impress\u00e3o",
        "Impress\u00e3o",
        "Marcenaria",
        "Acabamento",
        "Terceiriza\u00e7\u00e3o",
        "Expedi\u00e7\u00e3o",
        "Operacional",
    ]

    if Setor.query.first():
        return

    for nome in setores_nomes:
        db.session.add(Setor(nome=nome))
    db.session.commit()


def criar_usuarios_teste():
    if not User.query.filter_by(email="admin@teste.com").first():
        db.session.add(User(
            nome="Admin Teste",
            email="admin@teste.com",
            senha=generate_password_hash("123"),
            tipo="ADMIN",
            ativo=True
        ))

    if not User.query.filter_by(email="atendente@teste.com").first():
        db.session.add(User(
            nome="Atendente Teste",
            email="atendente@teste.com",
            senha=generate_password_hash("123"),
            tipo="ATENDENTE",
            ativo=True
        ))

    if not User.query.filter_by(email="pcp@teste.com").first():
        db.session.add(User(
            nome="PCP Teste",
            email="pcp@teste.com",
            senha=generate_password_hash("123"),
            tipo="PCP",
            ativo=True
        ))

    for setor in Setor.query.all():
        email = (
            f"{setor.nome.lower().replace(' ', '').replace('/', '').replace('-', '')}"
            "@teste.com"
        )
        if not User.query.filter_by(email=email).first():
            db.session.add(User(
                nome=f"Setor {setor.nome}",
                email=email,
                senha=generate_password_hash("123"),
                tipo="SETOR",
                setor_id=setor.id,
                ativo=True
            ))

    db.session.commit()


def initialize_database(app):
    if app_env() != "test":
        return

    with app.app_context():
        db.create_all()
        garantir_colunas_usuario()
        garantir_coluna_alta_prioridade()
        garantir_coluna_cliente_op()
        garantir_colunas_op_metricas()
        garantir_colunas_notificacao()
        garantir_colunas_tarefa()
        criar_setores_padrao()

        if ambiente_permite_seed_teste(app):
            criar_usuarios_teste()
