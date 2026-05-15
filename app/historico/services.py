from flask import session

from database.models import db, HistoricoOP


def usuario_atual():
    return session.get("usuario") or "Sistema"


def registrar_historico(op_id, acao, descricao):
    db.session.add(HistoricoOP(
        op_id=op_id,
        acao=acao,
        usuario=usuario_atual(),
        descricao=descricao
    ))
