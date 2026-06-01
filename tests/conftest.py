import gc
import os
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

gc.disable()

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["SECRET_KEY"] = "test-secret"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app as flask_app  # noqa: E402
from database.models import db, Notificacao, OP, OPSetor, Setor, Tarefa, User  # noqa: E402

_PYTEST_EXIT_STATUS = 0


def pytest_sessionfinish(session, exitstatus):
    global _PYTEST_EXIT_STATUS
    _PYTEST_EXIT_STATUS = exitstatus
    gc.disable()


def pytest_unconfigure(config):
    # Python 3.14 on this stack can crash during interpreter GC after importing
    # the Flask app. Preserve pytest's status and skip only that shutdown path.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_PYTEST_EXIT_STATUS)


@pytest.fixture()
def app():
    flask_app.config.update(TESTING=True, EMAILS_OPERACIONAIS_ATIVOS=False)

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        seed_base_data()
        yield flask_app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def seed_base_data():
    atendimento = Setor(nome="Atendimento")
    pcp = Setor(nome="PCP")
    acabamento = Setor(nome="Acabamento")
    db.session.add_all([atendimento, pcp, acabamento])
    db.session.flush()

    db.session.add_all([
        User(
            email="admin@teste.com",
            senha=generate_password_hash("123"),
            tipo="ADMIN",
            ativo=True
        ),
        User(
            email="atendente@teste.com",
            senha=generate_password_hash("123"),
            tipo="ATENDENTE",
            ativo=True
        ),
        User(
            email="pcp@teste.com",
            senha=generate_password_hash("123"),
            tipo="PCP",
            ativo=True
        ),
        User(
            email="setor@teste.com",
            senha=generate_password_hash("123"),
            tipo="SETOR",
            setor_id=acabamento.id,
            ativo=True
        ),
        User(
            email="espectador@teste.com",
            senha=generate_password_hash("123"),
            tipo="ESPECTADOR",
            ativo=True
        ),
        User(
            email="novo@teste.com",
            senha=None,
            tipo="ATENDENTE",
            ativo=False
        ),
    ])
    db.session.commit()


@pytest.fixture()
def setores(app):
    return {
        setor.nome: setor
        for setor in Setor.query.order_by(Setor.id).all()
    }


@pytest.fixture()
def login_as(client):
    def _login_as(tipo, email=None, setor_id=None):
        email_por_tipo = {
            "ADMIN": "admin@teste.com",
            "ATENDENTE": "atendente@teste.com",
            "PCP": "pcp@teste.com",
            "SETOR": "setor@teste.com",
            "ESPECTADOR": "espectador@teste.com",
        }

        with client.session_transaction() as sess:
            sess["usuario"] = email or email_por_tipo[tipo]
            sess["tipo"] = tipo
            sess["setor_id"] = setor_id

    return _login_as


@pytest.fixture()
def op_com_setor(app, setores):
    op = OP(
        nome="OP Teste",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com"
    )
    db.session.add(op)
    db.session.flush()

    setor = setores["Acabamento"]
    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    db.session.commit()

    return op, setor


@pytest.fixture()
def tarefa(app, op_com_setor):
    op, setor = op_com_setor
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Tarefa Teste",
        liberada=True
    )
    db.session.add(tarefa)
    db.session.commit()

    return tarefa


@pytest.fixture()
def notificacao(app, tarefa):
    notificacao = Notificacao(
        usuario="ATENDENTE",
        mensagem="Tarefa aguardando validacao",
        op_id=tarefa.op_id,
        tarefa_id=tarefa.id,
        setor_id=tarefa.setor_id,
        tipo_evento="tarefa_aguardando_validacao"
    )
    db.session.add(notificacao)
    db.session.commit()

    return notificacao
