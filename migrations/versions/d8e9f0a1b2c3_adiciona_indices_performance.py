"""adiciona indices prioritarios de performance

Revision ID: d8e9f0a1b2c3
Revises: b7c9a1d2e3f4
Create Date: 2026-06-01 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d8e9f0a1b2c3"
down_revision = "b7c9a1d2e3f4"
branch_labels = None
depends_on = None


INDEXES = (
    {
        "name": "ix_ops_status_prazo_final_id",
        "table": "ops",
        "columns": (("status", None), ("prazo_final", None), ("id", None)),
    },
    {
        "name": "ix_ops_prazo_final_status",
        "table": "ops",
        "columns": (("prazo_final", None), ("status", None)),
    },
    {
        "name": "ix_tarefas_op_id",
        "table": "tarefas",
        "columns": (("op_id", None),),
    },
    {
        "name": "ix_tarefas_prazo_validado",
        "table": "tarefas",
        "columns": (("prazo", None), ("validado", None)),
    },
    {
        "name": "ix_tarefas_entregue_validado",
        "table": "tarefas",
        "columns": (("entregue", None), ("validado", None)),
    },
    {
        "name": "ix_tarefas_setor_validado_prazo",
        "table": "tarefas",
        "columns": (("setor_id", None), ("validado", None), ("prazo", None)),
    },
    {
        "name": "ix_tarefa_responsaveis_usuario_status_ativo_tarefa",
        "table": "tarefa_responsaveis",
        "columns": (
            ("usuario_id", None),
            ("status", None),
            ("ativo", None),
            ("tarefa_id", None),
        ),
    },
    {
        "name": "ix_tarefa_responsaveis_tarefa_status_ativo",
        "table": "tarefa_responsaveis",
        "columns": (("tarefa_id", None), ("status", None), ("ativo", None)),
    },
    {
        "name": "ix_notificacoes_usuario_lida_data_desc",
        "table": "notificacoes",
        "columns": (("usuario", None), ("lida", None), ("data", "DESC")),
    },
    {
        "name": "ix_notificacoes_tipo_evento_tarefa_id",
        "table": "notificacoes",
        "columns": (("tipo_evento", None), ("tarefa_id", None)),
    },
    {
        "name": "ix_notificacoes_tipo_evento_op_id",
        "table": "notificacoes",
        "columns": (("tipo_evento", None), ("op_id", None)),
    },
    {
        "name": "ix_historico_op_op_id_data_desc",
        "table": "historico_op",
        "columns": (("op_id", None), ("data", "DESC")),
    },
)


def _quote_identifier(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _table_exists(inspector, table_name):
    return table_name in inspector.get_table_names()


def _columns_exist(inspector, table_name, columns):
    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }
    return all(column_name in existing_columns for column_name, _order in columns)


def _index_exists(inspector, table_name, index_name, columns):
    requested_columns = tuple(column_name for column_name, _order in columns)

    for index in inspector.get_indexes(table_name):
        if index["name"] == index_name:
            return True

        existing_columns = tuple(
            column_name
            for column_name in (index.get("column_names") or ())
            if column_name
        )
        if existing_columns == requested_columns:
            return True

    return False


def _column_sql(columns):
    parts = []
    for column_name, order in columns:
        part = _quote_identifier(column_name)
        if order:
            part = f"{part} {order}"
        parts.append(part)
    return ", ".join(parts)


def _create_index(index):
    op.execute(sa.text(
        "CREATE INDEX "
        f"{_quote_identifier(index['name'])} "
        f"ON {_quote_identifier(index['table'])} "
        f"({_column_sql(index['columns'])})"
    ))


def upgrade():
    inspector = sa.inspect(op.get_bind())

    for index in INDEXES:
        table_name = index["table"]
        columns = index["columns"]

        if not _table_exists(inspector, table_name):
            continue

        if not _columns_exist(inspector, table_name, columns):
            continue

        if _index_exists(inspector, table_name, index["name"], columns):
            continue

        _create_index(index)


def downgrade():
    for index in reversed(INDEXES):
        op.execute(sa.text(
            f"DROP INDEX IF EXISTS {_quote_identifier(index['name'])}"
        ))
