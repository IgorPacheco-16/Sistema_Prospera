from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


#USUÁRIOS
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    senha = db.Column(db.String(100), nullable=True)
    tipo = db.Column(db.String(20))

    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id'))
    setor = db.relationship('Setor')


    ativo = db.Column(db.Boolean, default=False)


#ORDEM DE PRODUÇÃO
class OP(db.Model):
    __tablename__ = "ops"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    prazo_final = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=False, default="ABERTA")
    atendente = db.Column(db.String(100), nullable=False)
    alta_prioridade = db.Column(db.Boolean, nullable=False, default=False)

    tarefas = db.relationship(
        "Tarefa",
        backref="op",
        cascade="all, delete-orphan",
        lazy=True
    )


#SETORES
class Setor(db.Model):
    __tablename__ = "setor"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)


#RELAÇÃO OP x SETOR
class OPSetor(db.Model):
    __tablename__ = "op_setor"

    id = db.Column(db.Integer, primary_key=True)

    op_id = db.Column(db.Integer, db.ForeignKey("ops.id"), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey("setor.id"), nullable=False)

    op = db.relationship("OP", backref="op_setores")
    setor = db.relationship("Setor")


#TAREFAS
class Tarefa(db.Model):
    __tablename__ = "tarefas"

    id = db.Column(db.Integer, primary_key=True)

    op_id = db.Column(
        db.Integer,
        db.ForeignKey("ops.id"),  # 👈 já estava certo
        nullable=False
    )

    setor_id = db.Column(
        db.Integer,
        db.ForeignKey("setor.id"),
        nullable=False
    )

    nome = db.Column(db.String(200), nullable=False)
    prazo = db.Column(db.Date, nullable=True)

    liberada = db.Column(db.Boolean, default=True)
    entregue = db.Column(db.Boolean, default=False)
    validado = db.Column(db.Boolean, default=False)

    setor = db.relationship('Setor')


#NOTIFICAÇÕES
class Notificacao(db.Model):
    __tablename__ = "notificacoes"

    id = db.Column(db.Integer, primary_key=True)

    usuario = db.Column(db.String(100), nullable=False)
    mensagem = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    op_id = db.Column(db.Integer, nullable=True)
    tarefa_id = db.Column(db.Integer, nullable=True)
    setor_id = db.Column(db.Integer, nullable=True)
    tipo_evento = db.Column(db.String(80), nullable=True)

    lida = db.Column(db.Boolean, default=False)

    data = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )


#HISTORICO DE ACOES DA OP
class HistoricoOP(db.Model):
    __tablename__ = "historico_op"

    id = db.Column(db.Integer, primary_key=True)
    op_id = db.Column(db.Integer, db.ForeignKey("ops.id"), nullable=False)
    acao = db.Column(db.String(80), nullable=False)
    usuario = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    data = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    op = db.relationship("OP")
