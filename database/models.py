from flask_sqlalchemy import SQLAlchemy
from tempo import agora_brasilia

db = SQLAlchemy()


tarefa_responsaveis = db.Table(
    "tarefa_responsaveis",
    db.Column(
        "tarefa_id",
        db.Integer,
        db.ForeignKey("tarefas.id", ondelete="CASCADE"),
        primary_key=True
    ),
    db.Column(
        "user_id",
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    ),
)


#USUÁRIOS
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), unique=True)
    senha = db.Column(db.String(255), nullable=True)
    tipo = db.Column(db.String(20))

    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id'))
    setor = db.relationship('Setor')


    ativo = db.Column(db.Boolean, default=False)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    codigo_hash = db.Column(db.String(255), nullable=False)
    expira_em = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(
        db.DateTime,
        default=agora_brasilia,
        nullable=False
    )

    user = db.relationship("User")


class CadastroPendente(db.Model):
    __tablename__ = "cadastros_pendentes"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    codigo_hash = db.Column(db.String(255), nullable=False)
    expira_em = db.Column(db.DateTime, nullable=False)
    tentativas = db.Column(db.Integer, default=0, nullable=False)
    verificado = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(
        db.DateTime,
        default=agora_brasilia,
        nullable=False
    )


#ORDEM DE PRODUÇÃO
class OP(db.Model):
    __tablename__ = "ops"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    cliente = db.Column(db.String(200), nullable=True)
    prazo_final = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=False, default="ABERTA")
    atendente = db.Column(db.String(100), nullable=False)
    alta_prioridade = db.Column(db.Boolean, nullable=False, default=False)
    caminho_pasta = db.Column(db.String(500), nullable=True)
    criada_em = db.Column(db.DateTime, default=agora_brasilia, nullable=True)
    finalizada_em = db.Column(db.DateTime, nullable=True)
    arquivada_em = db.Column(db.DateTime, nullable=True)

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

    status = db.Column(db.String(30), nullable=False, default="PENDENTE")
    liberada = db.Column(db.Boolean, default=True)
    entregue = db.Column(db.Boolean, default=False)
    validado = db.Column(db.Boolean, default=False)
    criada_em = db.Column(db.DateTime, default=agora_brasilia, nullable=True)
    iniciada_em = db.Column(db.DateTime, nullable=True)
    enviada_validacao_em = db.Column(db.DateTime, nullable=True)
    validada_em = db.Column(db.DateTime, nullable=True)
    recusada_em = db.Column(db.DateTime, nullable=True)
    entregue_em = db.Column(db.DateTime, nullable=True)
    concluida_em = db.Column(db.DateTime, nullable=True)
    motivo_recusa = db.Column(db.String(255), nullable=True)
    setor = db.relationship('Setor')
    responsaveis = db.relationship(
        'User',
        secondary=tarefa_responsaveis,
        backref=db.backref('tarefas_responsaveis', lazy='dynamic'),
        order_by='User.nome',
    )


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
    email_enviado = db.Column(db.Boolean, default=False, nullable=False)

    data = db.Column(
        db.DateTime,
        default=agora_brasilia,
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
        default=agora_brasilia,
        nullable=False
    )

    op = db.relationship("OP")
