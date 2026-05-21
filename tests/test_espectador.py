from datetime import timedelta

from database.models import db, OP, OPSetor, Tarefa
from tempo import hoje_brasilia


def criar_op_com_tarefa(setor, status_tarefa="PENDENTE"):
    op = OP(
        nome="OP Visivel Espectador",
        status="EM ANDAMENTO",
        atendente="atendente@teste.com",
        prazo_final=hoje_brasilia() + timedelta(days=3),
    )
    db.session.add(op)
    db.session.flush()

    db.session.add(OPSetor(op_id=op.id, setor_id=setor.id))
    tarefa = Tarefa(
        op_id=op.id,
        setor_id=setor.id,
        nome="Tarefa Visivel Espectador",
        prazo=hoje_brasilia() + timedelta(days=1),
        status=status_tarefa,
        liberada=True,
    )
    db.session.add(tarefa)
    db.session.commit()

    return op, tarefa


def test_espectador_acessa_dashboard_kanban_calendario_e_detalhe_op(client, login_as, setores):
    op, _tarefa = criar_op_com_tarefa(setores["Acabamento"])
    login_as("ESPECTADOR")

    for caminho in ["/dashboard", "/kanban", "/calendario", f"/op/{op.id}"]:
        resposta = client.get(caminho)

        assert resposta.status_code == 200


def test_espectador_nao_acessa_criar_ou_editar_op(client, login_as, setores):
    op, _tarefa = criar_op_com_tarefa(setores["Acabamento"])
    login_as("ESPECTADOR")

    resposta_criar = client.get("/criar_op")
    resposta_editar = client.get(f"/editar_op/{op.id}")

    assert resposta_criar.status_code == 403
    assert resposta_editar.status_code == 403


def test_espectador_nao_acessa_gestao_de_usuarios(client, login_as):
    login_as("ESPECTADOR")

    resposta_lista = client.get("/usuarios")
    resposta_criar = client.get("/criar_usuario")

    assert resposta_lista.status_code == 403
    assert resposta_criar.status_code == 403


def test_espectador_nao_executa_post_de_tarefa(client, login_as, setores):
    op, tarefa = criar_op_com_tarefa(setores["Acabamento"])
    login_as("ESPECTADOR")

    resposta = client.post(
        f"/iniciar_tarefa/{tarefa.id}",
        headers={"Referer": f"/op/{op.id}"}
    )

    assert resposta.status_code == 403


def test_espectador_nao_ve_botoes_de_acao_principais(client, login_as, setores):
    op, tarefa = criar_op_com_tarefa(setores["Acabamento"], status_tarefa="PENDENTE")
    login_as("ESPECTADOR")

    dashboard = client.get("/dashboard").get_data(as_text=True)
    detalhe = client.get(f"/op/{op.id}").get_data(as_text=True)

    assert "Nova OP" not in dashboard
    assert "Gerenciar usuarios" not in dashboard
    assert "Cadastrar usuario" not in dashboard
    assert "Arquivar" not in dashboard
    assert "Arquivadas" not in dashboard

    assert "Editar OP" not in detalhe
    assert "OP finalizada" not in detalhe
    assert "Adicionar" not in detalhe
    assert "Editar" not in detalhe
    assert "Iniciar" not in detalhe
    assert "Enviar para valida" not in detalhe
    assert "Validar" not in detalhe
    assert "Recusar" not in detalhe
    assert "Excluir tarefa" not in detalhe
    assert f'action="/iniciar_tarefa/{tarefa.id}"' not in detalhe


def test_link_slides_aparece_para_perfis_permitidos_e_nao_para_setor(client, login_as, setores):
    for tipo in ["ADMIN", "PCP", "ATENDENTE", "ESPECTADOR"]:
        login_as(tipo)
        html = client.get("/dashboard").get_data(as_text=True)

        assert 'href="/slides"' in html
        assert "Slides" in html

    login_as("SETOR", setor_id=setores["Acabamento"].id)
    html = client.get("/dashboard").get_data(as_text=True)

    assert 'href="/slides"' not in html
    assert "Slides" not in html
