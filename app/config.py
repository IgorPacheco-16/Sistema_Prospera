import os
import secrets

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from database.models import db, Setor, User


def configure_app(app):
    flask_env = os.environ.get("FLASK_ENV")
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if flask_env == "development":
            secret_key = secrets.token_hex(32)
        else:
            raise RuntimeError(
                "SECRET_KEY obrigatoria em producao. "
                "Defina a variavel de ambiente SECRET_KEY."
            )

    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        os.environ.get("DATABASE_URL") or "sqlite:///database.db"
    )


def garantir_coluna_alta_prioridade():
    colunas = db.session.execute(text("PRAGMA table_info(ops)")).fetchall()
    nomes_colunas = [coluna[1] for coluna in colunas]

    if "alta_prioridade" not in nomes_colunas:
        try:
            db.session.execute(text(
                "ALTER TABLE ops "
                "ADD COLUMN alta_prioridade BOOLEAN NOT NULL DEFAULT 0"
            ))
            db.session.commit()
        except OperationalError as erro:
            db.session.rollback()
            if "duplicate column name" not in str(erro).lower():
                raise


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


def garantir_colunas_notificacao():
    adicionar_coluna_se_nao_existir("notificacoes", "link", "VARCHAR(255)")
    adicionar_coluna_se_nao_existir("notificacoes", "op_id", "INTEGER")
    adicionar_coluna_se_nao_existir("notificacoes", "tarefa_id", "INTEGER")
    adicionar_coluna_se_nao_existir("notificacoes", "setor_id", "INTEGER")
    adicionar_coluna_se_nao_existir("notificacoes", "tipo_evento", "VARCHAR(80)")


def initialize_database(app):
    with app.app_context():
        db.create_all()
        garantir_coluna_alta_prioridade()
        garantir_colunas_notificacao()

        setores_nomes = [
            "Atendimento", "Criação", "Projeto", "Compras/Estoque", "PCP",
            "Arte Final", "Pré-impressão", "Impressão", "Marcenaria",
            "Acabamento", "Terceirização", "Expedição", "Operacional"
        ]

        if not Setor.query.first():
            for nome in setores_nomes:
                db.session.add(Setor(nome=nome))
            db.session.commit()

        if not User.query.filter_by(email="admin@teste.com").first():
            db.session.add(User(
                email="admin@teste.com",
                senha=generate_password_hash("123"),
                tipo="ADMIN",
                ativo=True
            ))

        igor_admin = User.query.filter_by(email="igorpacheconsantos@gmail.com").first()
        if not igor_admin:
            db.session.add(User(
                email="igorpacheconsantos@gmail.com",
                senha=generate_password_hash("123"),
                tipo="ADMIN",
                ativo=True
            ))
        else:
            igor_admin.tipo = "ADMIN"
            igor_admin.ativo = True
            if not igor_admin.senha:
                igor_admin.senha = generate_password_hash("123")

        if not User.query.filter_by(email="atendente@teste.com").first():
            db.session.add(User(
                email="atendente@teste.com",
                senha=generate_password_hash("123"),
                tipo="ATENDENTE",
                ativo=True
            ))

        if not User.query.filter_by(email="pcp@teste.com").first():
            db.session.add(User(
                email="pcp1@teste.com",
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
                    email=email,
                    senha=generate_password_hash("123"),
                    tipo="SETOR",
                    setor_id=setor.id,
                    ativo=True
                ))

        db.session.commit()
