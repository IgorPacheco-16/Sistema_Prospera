from flask_sqlalchemy import SQLAlchemy
from tempo import agora_brasilia

db = SQLAlchemy()


tarefa_responsaveis = db.Table(
    "tarefa_responsaveis",
    db.Column("id", db.Integer, primary_key=True),
    db.Column(
        "tarefa_id",
        db.Integer,
        db.ForeignKey("tarefas.id", ondelete="CASCADE"),
        nullable=False
    ),
    db.Column(
        "usuario_id",
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    ),
    db.Column("status", db.String(20), nullable=False, default="ACEITO", server_default="ACEITO"),
    db.Column("tipo", db.String(20), nullable=False, default="ATRIBUICAO", server_default="ATRIBUICAO"),
    db.Column("solicitado_por_id", db.Integer, db.ForeignKey("users.id"), nullable=True),
    db.Column("solicitado_em", db.DateTime, default=agora_brasilia, nullable=False),
    db.Column("respondido_em", db.DateTime, nullable=True),
    db.Column("observacao", db.String(1000), nullable=True),
    db.Column("ativo", db.Boolean, default=True, nullable=False, server_default="1"),
    db.Column("repasse_lote_id", db.String(36), nullable=True),
    db.Column("repasse_papel", db.String(20), nullable=True),
    db.Column("repasse_status", db.String(20), nullable=True),
)


class TarefaResponsavel(db.Model):
    __table__ = tarefa_responsaveis

    tarefa = db.relationship(
        "Tarefa",
        back_populates="responsavel_vinculos",
        overlaps="responsaveis,tarefas_responsaveis"
    )
    usuario = db.relationship(
        "User",
        foreign_keys=[tarefa_responsaveis.c.usuario_id],
        overlaps="responsaveis,tarefas_responsaveis"
    )
    solicitado_por = db.relationship(
        "User",
        foreign_keys=[tarefa_responsaveis.c.solicitado_por_id],
    )

    def esta_pendente(self):
        return self.ativo and self.status == "PENDENTE"

    def esta_aceito(self):
        return self.ativo and self.status == "ACEITO"


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
    observacao_entrega = db.Column(db.String(1000), nullable=True)
    motivo_recusa = db.Column(db.String(255), nullable=True)
    em_espera = db.Column(db.Boolean, default=False, nullable=False, server_default="0")
    espera_motivo_atual = db.Column(db.String(1000), nullable=True)
    espera_aprovada_em = db.Column(db.DateTime, nullable=True)
    espera_aprovada_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    espera_solicitacao_atual_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "tarefa_espera_solicitacoes.id",
            use_alter=True,
            name="fk_tarefas_espera_solicitacao_atual_id",
        ),
        nullable=True,
    )
    setor = db.relationship('Setor')
    espera_aprovada_por = db.relationship(
        "User",
        foreign_keys=[espera_aprovada_por_id],
    )
    espera_solicitacao_atual = db.relationship(
        "TarefaEsperaSolicitacao",
        foreign_keys=[espera_solicitacao_atual_id],
        post_update=True,
    )
    espera_solicitacoes = db.relationship(
        "TarefaEsperaSolicitacao",
        back_populates="tarefa",
        cascade="all, delete-orphan",
        foreign_keys="TarefaEsperaSolicitacao.tarefa_id",
        order_by="TarefaEsperaSolicitacao.solicitado_em, TarefaEsperaSolicitacao.id",
    )
    responsavel_vinculos = db.relationship(
        "TarefaResponsavel",
        back_populates="tarefa",
        cascade="all, delete-orphan",
        order_by="TarefaResponsavel.solicitado_em, TarefaResponsavel.id",
        overlaps="responsaveis,tarefas_responsaveis",
    )
    responsaveis = db.relationship(
        'User',
        secondary=tarefa_responsaveis,
        primaryjoin=(
            "and_(Tarefa.id == tarefa_responsaveis.c.tarefa_id, "
            "tarefa_responsaveis.c.status == 'ACEITO', "
            "tarefa_responsaveis.c.ativo == True)"
        ),
        secondaryjoin="User.id == tarefa_responsaveis.c.usuario_id",
        backref=db.backref('tarefas_responsaveis', lazy='dynamic'),
        order_by='User.nome',
        overlaps="responsavel_vinculos,tarefa,usuario",
    )


#NOTIFICAÇÕES
class TarefaEsperaSolicitacao(db.Model):
    __tablename__ = "tarefa_espera_solicitacoes"

    id = db.Column(db.Integer, primary_key=True)
    tarefa_id = db.Column(
        db.Integer,
        db.ForeignKey("tarefas.id", ondelete="CASCADE"),
        nullable=False,
    )
    solicitado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    motivo = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="PENDENTE", server_default="PENDENTE")
    respondido_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    solicitado_em = db.Column(db.DateTime, default=agora_brasilia, nullable=False)
    respondido_em = db.Column(db.DateTime, nullable=True)
    justificativa_resposta = db.Column(db.String(1000), nullable=True)
    status_anterior_tarefa = db.Column(db.String(30), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False, server_default="1")

    tarefa = db.relationship(
        "Tarefa",
        back_populates="espera_solicitacoes",
        foreign_keys=[tarefa_id],
    )
    solicitado_por = db.relationship(
        "User",
        foreign_keys=[solicitado_por_id],
    )
    respondido_por = db.relationship(
        "User",
        foreign_keys=[respondido_por_id],
    )

    def esta_pendente(self):
        return self.ativo and self.status == "PENDENTE"


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


class NotificationEmailDelivery(db.Model):
    __tablename__ = "notification_email_deliveries"

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(50), nullable=False, default="relatorio_operacional")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    recipient_email = db.Column(db.String(100), nullable=False)
    janela = db.Column(db.String(10), nullable=False)
    data_operacional = db.Column(db.Date, nullable=False)
    content_hash = db.Column(db.String(64), nullable=True)
    content_summary = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False)
    erro = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=agora_brasilia,
        nullable=False
    )
    sent_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")


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
