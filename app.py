from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify, flash
from database.models import db, User, OP, Tarefa, Notificacao, Setor, OPSetor, HistoricoOP
from datetime import datetime, date
import importlib.util
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent


def carregar_variaveis_ambiente():
    env_path = BASE_DIR / ".env"
    fallback_env_path = BASE_DIR / "shounen.env"
    caminho_env = None

    if env_path.exists():
        caminho_env = env_path
    elif fallback_env_path.exists():
        caminho_env = fallback_env_path

    if not caminho_env:
        return

    if load_dotenv:
        load_dotenv(dotenv_path=caminho_env)
        return

    for linha in caminho_env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue

        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


def carregar_modulo(nome, caminho_relativo):
    caminho = BASE_DIR / caminho_relativo
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


carregar_variaveis_ambiente()

config_module = carregar_modulo("pacheco_config", "app/config.py")
security_module = carregar_modulo("pacheco_security", "app/security.py")
historico_module = carregar_modulo("pacheco_historico_services", "app/historico/services.py")
notificacoes_module = carregar_modulo("pacheco_notificacoes_services", "app/notificacoes/services.py")
notificacoes_routes_module = carregar_modulo("pacheco_notificacoes_routes", "app/notificacoes/routes.py")
auth_routes_module = carregar_modulo("pacheco_auth_routes", "app/auth/routes.py")
usuarios_routes_module = carregar_modulo("pacheco_usuarios_routes", "app/usuarios/routes.py")
dashboard_routes_module = carregar_modulo("pacheco_dashboard_routes", "app/dashboard/routes.py")
calendario_routes_module = carregar_modulo("pacheco_calendario_routes", "app/calendario/routes.py")
ops_routes_module = carregar_modulo("pacheco_ops_routes", "app/ops/routes.py")

configure_app = config_module.configure_app
initialize_database = config_module.initialize_database

is_admin = security_module.is_admin
is_atendente = security_module.is_atendente
is_pcp = security_module.is_pcp
is_setor = security_module.is_setor
login_required = security_module.login_required
tipos_permitidos = security_module.tipos_permitidos
normalizar_email = security_module.normalizar_email
gerar_codigo_recuperacao = security_module.gerar_codigo_recuperacao
enviar_email_recuperacao = security_module.enviar_email_recuperacao

registrar_historico = historico_module.registrar_historico

link_op = notificacoes_module.link_op
link_tarefa = notificacoes_module.link_tarefa
query_notificacoes_usuario = notificacoes_module.query_notificacoes_usuario
criar_notificacao = notificacoes_module.criar_notificacao
gerar_notificacoes_pendentes = notificacoes_module.gerar_notificacoes_pendentes
create_notificacoes_blueprint = notificacoes_routes_module.create_notificacoes_blueprint
create_auth_blueprint = auth_routes_module.create_auth_blueprint
create_usuarios_blueprint = usuarios_routes_module.create_usuarios_blueprint
create_dashboard_blueprint = dashboard_routes_module.create_dashboard_blueprint
create_calendario_blueprint = calendario_routes_module.create_calendario_blueprint
create_ops_blueprint = ops_routes_module.create_ops_blueprint

app = Flask(__name__)
configure_app(app)
db.init_app(app)

initialize_database(app)

auth_bp = create_auth_blueprint(
    login_required=login_required,
    normalizar_email=normalizar_email,
    gerar_codigo_recuperacao=gerar_codigo_recuperacao,
    enviar_email_recuperacao=enviar_email_recuperacao
)
app.register_blueprint(auth_bp)

app.add_url_rule("/", endpoint="login", build_only=True)
app.add_url_rule("/logout", endpoint="logout", build_only=True)
app.add_url_rule("/esqueci_senha", endpoint="esqueci_senha", build_only=True)
app.add_url_rule("/redefinir_senha", endpoint="redefinir_senha", build_only=True)
app.add_url_rule("/definir_senha", endpoint="definir_senha", build_only=True)

usuarios_bp = create_usuarios_blueprint(
    login_required=login_required,
    tipos_permitidos=tipos_permitidos,
    normalizar_email=normalizar_email
)
app.register_blueprint(usuarios_bp)

app.add_url_rule("/criar_usuario", endpoint="criar_usuario", build_only=True)
app.add_url_rule("/minha_conta", endpoint="minha_conta", build_only=True)

notificacoes_bp = create_notificacoes_blueprint(
    login_required=login_required,
    is_setor=is_setor,
    gerar_notificacoes_pendentes=gerar_notificacoes_pendentes,
    query_notificacoes_usuario=query_notificacoes_usuario,
    criar_notificacao=criar_notificacao
)
app.register_blueprint(notificacoes_bp)

app.add_url_rule("/notificacoes", endpoint="notificacoes", build_only=True)
app.add_url_rule("/ler_notificacao/<int:id>", endpoint="ler_notificacao", build_only=True)
app.add_url_rule("/api/notificacoes", endpoint="api_notificacoes", build_only=True)
app.add_url_rule("/teste_notificacao", endpoint="teste_notificacao", build_only=True)

dashboard_bp = create_dashboard_blueprint(
    login_required=login_required,
    gerar_notificacoes_pendentes=gerar_notificacoes_pendentes
)
app.register_blueprint(dashboard_bp)

calendario_bp = create_calendario_blueprint(login_required=login_required)
app.register_blueprint(calendario_bp)

ops_bp = create_ops_blueprint(login_required=login_required)
app.register_blueprint(ops_bp)

app.add_url_rule("/dashboard", endpoint="dashboard", build_only=True)
app.add_url_rule("/calendario", endpoint="calendario", build_only=True)
app.add_url_rule("/arquivadas", endpoint="arquivadas", build_only=True)

@app.before_request
def before():
    pass

@app.context_processor
def inject_notificacoes():
    if "tipo" in session:
        notificacoes_nao_lidas = query_notificacoes_usuario().filter_by(lida=False).count()

        notificacoes_recentes = query_notificacoes_usuario().order_by(
            Notificacao.data.desc()
        ).limit(8).all()

        return dict(
            total_notificacoes=notificacoes_nao_lidas,
            notificacoes_recentes=notificacoes_recentes
        )

#Rota e função para a criação das novas OPs

@app.route("/criar_op", methods=["GET", "POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def criar_op():
    if request.method == "POST":
        nome = request.form.get("nome")
        prazo = request.form.get("prazo")
        alta_prioridade = request.form.get("alta_prioridade") == "on"
        setores = request.form.getlist("setores")

        prazo_convertido = None
        if prazo:
            prazo_convertido = datetime.strptime(prazo, "%Y-%m-%d").date()

        nova_op = OP(
            nome=nome,
            prazo_final=prazo_convertido,
            status="EM ANDAMENTO",
            atendente=session.get("usuario"),
            alta_prioridade=alta_prioridade
        )

        db.session.add(nova_op)
        db.session.commit()

        for setor_id in setores:
            db.session.add(OPSetor(
                op_id=nova_op.id,
                setor_id=int(setor_id)
            ))

        criar_notificacao(
            "PCP",
            f"Nova OP criada: OP #{nova_op.id} - {nova_op.nome}",
            link=link_op(nova_op.id),
            op_id=nova_op.id,
            tipo_evento="op_criada"
        )
        registrar_historico(
            nova_op.id,
            "OP criada",
            f"OP criada com {len(setores)} setor(es) participante(s)."
        )

        db.session.commit()

        return redirect(url_for("ver_op", id=nova_op.id))

    return render_template("op/criar.html", setores=Setor.query.all())

#Rota para entrada da aba das OPs e tudo mais

@app.route("/op/<int:id>")
@login_required
def ver_op(id):
    op = db.session.get(OP, id)
    if not op:
        abort(404)

    estrutura = []

    for op_setor in op.op_setores:
        setor = op_setor.setor

        tarefas = Tarefa.query.filter_by(
            op_id=op.id,
            setor_id=setor.id
        ).all()

        estrutura.append({
            "setor": setor,
            "tarefas": tarefas,
            "total": len(tarefas),
            "validadas": sum(1 for t in tarefas if t.validado)
        })

    historico = HistoricoOP.query.filter_by(
        op_id=op.id
    ).order_by(HistoricoOP.data.desc()).limit(30).all()

    return render_template(
        "op/detalhe.html",
        op=op,
        estrutura=estrutura,
        historico=historico,
        setores=Setor.query.all(),
        tipo=session.get("tipo"),
        today=date.today(),
        focus_setor_id=request.args.get("setor", type=int),
        focus_tarefa_id=request.args.get("tarefa", type=int)
    )

#Rota feita para a parte de criação de novas tarefas

@app.route("/criar_tarefa/<int:op_id>/<int:setor_id>", methods=["POST"])
@tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
def criar_tarefa(op_id, setor_id):
    setor_vinculado = OPSetor.query.filter_by(
        op_id=op_id,
        setor_id=setor_id
    ).first()

    if not setor_vinculado:
        return "Setor não vinculado a esta OP", 400

    nome = request.form.get("nome")
    prazo = request.form.get("prazo")

    nova = Tarefa(
        op_id=op_id,
        setor_id=setor_id,
        nome=nome,
        prazo=datetime.strptime(prazo, "%Y-%m-%d").date() if prazo else None,
        liberada=True
    )

    db.session.add(nova)
    db.session.flush()

    op = db.session.get(OP, op_id)
    if op:
        criar_notificacao(
            "SETOR",
            f"Nova tarefa criada: {nova.nome} na OP #{op.id} - {op.nome}",
            link=link_tarefa(op.id, setor_id, nova.id),
            op_id=op.id,
            tarefa_id=nova.id,
            setor_id=setor_id,
            tipo_evento="tarefa_criada"
        )
        registrar_historico(
            op.id,
            "Tarefa criada",
            f"Tarefa '{nova.nome}' criada para o setor {setor_vinculado.setor.nome}."
        )

    db.session.commit()

    return redirect(request.referrer)

#Rota para a entrega de tarefas

@app.route("/entregar_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("SETOR", "ADMIN")
def entregar_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)

    if is_setor() and session.get("setor_id") != tarefa.setor_id:
        return "Setor incorreto", 403

    tarefa.entregue = True
    tarefa.validado = False

    op = db.session.get(OP, tarefa.op_id)
    if op:
        mensagem = f"Tarefa entregue aguardando validação: {tarefa.setor.nome} na OP #{op.id} - {op.nome}"
        link = link_tarefa(op.id, tarefa.setor_id, tarefa.id)
        criar_notificacao(
            "ATENDENTE",
            mensagem,
            link=link,
            op_id=op.id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="tarefa_aguardando_validacao"
        )
        criar_notificacao(
            "PCP",
            mensagem,
            link=link,
            op_id=op.id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="tarefa_aguardando_validacao"
        )
        registrar_historico(
            op.id,
            "Tarefa aguardando validação",
            f"Tarefa '{tarefa.nome}' enviada para validação pelo setor {tarefa.setor.nome}."
        )

    db.session.commit()

    return redirect(request.referrer)

#Rota para quem tiver permissão de atendente validar as tarefas entregues

@app.route("/validar_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def validar_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)

    if not tarefa.entregue:
        return "Precisa entregar antes"

    tarefa.validado = True

    op = db.session.get(OP, tarefa.op_id)
    if op:
        criar_notificacao(
            "SETOR",
            f"Entrega validada: {tarefa.nome} na OP #{op.id} - {op.nome}",
            link=link_tarefa(op.id, tarefa.setor_id, tarefa.id),
            op_id=op.id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="entrega_validada"
        )
        registrar_historico(
            op.id,
            "Entrega validada",
            f"Entrega da tarefa '{tarefa.nome}' validada."
        )

    db.session.commit()

    return redirect(request.referrer)

#Rota para as Ops que estão arquivadas

@app.route("/arquivar_op/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def arquivar_op(id):
    op = db.session.get(OP, id)
    if not op:
        abort(404)

    op.status = "ARQUIVADA"
    registrar_historico(
        op.id,
        "OP arquivada",
        "OP arquivada."
    )
    db.session.commit()
    return redirect(url_for("dashboard"))

#Rota para a exclusão das ops que estão arquivadas

@app.route("/excluir_op/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def excluir_op(id):
    op = db.session.get(OP, id)
    if not op:
        abort(404)

    Tarefa.query.filter_by(op_id=id).delete()
    OPSetor.query.filter_by(op_id=id).delete()
    HistoricoOP.query.filter_by(op_id=id).delete()
    Notificacao.query.filter_by(op_id=id).delete()
    db.session.delete(op)
    db.session.commit()

    return redirect(url_for("arquivadas"))

@app.route("/desarquivar_op/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def desarquivar_op(id):
    op = db.session.get(OP, id)
    if not op:
        abort(404)

    op.status = "EM ANDAMENTO"
    registrar_historico(
        op.id,
        "OP desarquivada",
        "OP desarquivada e devolvida para em andamento."
    )
    db.session.commit()
    return redirect(url_for("arquivadas"))

#Rota para a edição de OPs já abertas (Preciso mexer nisso)

@app.route("/editar_op/<int:id>", methods=["GET", "POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def editar_op(id):
    pode_editar_op = is_atendente() or is_admin()

    op = db.session.get(OP, id)
    if not op:
        abort(404)

    setores = Setor.query.all()

    if request.method == "POST":
        nome_anterior = op.nome
        prazo_anterior = op.prazo_final
        prioridade_anterior = op.alta_prioridade

        op.nome = request.form.get("nome")
        op.alta_prioridade = request.form.get("alta_prioridade") == "on"

        prazo = request.form.get("prazo")
        if prazo:
            op.prazo_final = datetime.strptime(prazo, "%Y-%m-%d").date()
        else:
            op.prazo_final = None

        setores_selecionados = {int(setor_id) for setor_id in request.form.getlist("setores")}
        setores_atuais = {op_setor.setor_id for op_setor in op.op_setores}

        for setor_id in setores_selecionados - setores_atuais:
            setor = db.session.get(Setor, setor_id)
            db.session.add(OPSetor(
                op_id=op.id,
                setor_id=setor_id
            ))
            registrar_historico(
                op.id,
                "Setor adicionado",
                f"Setor {setor.nome if setor else setor_id} adicionado à OP."
            )

        for op_setor in list(op.op_setores):
            if op_setor.setor_id in setores_selecionados:
                continue

            tem_tarefas = Tarefa.query.filter_by(
                op_id=op.id,
                setor_id=op_setor.setor_id
            ).first()

            if tem_tarefas:
                flash(
                    "Um ou mais setores com tarefas foram mantidos para proteger os dados da OP."
                )
            else:
                nome_setor = op_setor.setor.nome if op_setor.setor else op_setor.setor_id
                db.session.delete(op_setor)
                registrar_historico(
                    op.id,
                    "Setor removido",
                    f"Setor {nome_setor} removido da OP."
                )

        mudancas = []
        if nome_anterior != op.nome:
            mudancas.append("nome")
        if prazo_anterior != op.prazo_final:
            mudancas.append("prazo final")
        if prioridade_anterior != op.alta_prioridade:
            mudancas.append("alta prioridade")

        if mudancas:
            registrar_historico(
                op.id,
                "OP editada",
                "Dados da OP editados: " + ", ".join(mudancas) + "."
            )

        db.session.commit()
        return redirect(url_for("ver_op", id=op.id))

    return render_template(
        "op/editar.html",
        op=op,
        setores=setores,
        tipo=session.get("tipo"),
        pode_editar_op=pode_editar_op
    )


#Rota para edição de tarefas (diferente de editar uma OP, tbm preciso mexer nisso)

@app.route("/editar_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
def editar_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)
    nome_anterior = tarefa.nome
    prazo_anterior = tarefa.prazo

    tarefa.nome = request.form.get("nome")

    prazo = request.form.get("prazo")
    if prazo:
        tarefa.prazo = datetime.strptime(prazo, "%Y-%m-%d").date()
    else:
        tarefa.prazo = None

    mudancas = []
    if nome_anterior != tarefa.nome:
        mudancas.append("nome")
    if prazo_anterior != tarefa.prazo:
        mudancas.append("prazo")

    if mudancas:
        registrar_historico(
            tarefa.op_id,
            "Tarefa editada",
            f"Tarefa '{tarefa.nome}' editada: {', '.join(mudancas)}."
        )

    db.session.commit()
    return redirect(request.referrer)


@app.route("/excluir_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
def excluir_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)
    op_id = tarefa.op_id
    nome_tarefa = tarefa.nome
    nome_setor = tarefa.setor.nome if tarefa.setor else tarefa.setor_id

    db.session.delete(tarefa)
    registrar_historico(
        op_id,
        "Tarefa excluída",
        f"Tarefa '{nome_tarefa}' do setor {nome_setor} excluída."
    )
    db.session.commit()

    return redirect(url_for("ver_op", id=op_id))

@app.route("/recusar_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def recusar_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)
    tarefa.entregue = False
    tarefa.validado = False

    op = db.session.get(OP, tarefa.op_id)
    if op:
        criar_notificacao(
            "SETOR",
            f"Entrega recusada: {tarefa.nome} na OP #{op.id} - {op.nome}",
            link=link_tarefa(op.id, tarefa.setor_id, tarefa.id),
            op_id=op.id,
            tarefa_id=tarefa.id,
            setor_id=tarefa.setor_id,
            tipo_evento="entrega_recusada"
        )
        registrar_historico(
            op.id,
            "Entrega recusada",
            f"Entrega da tarefa '{tarefa.nome}' recusada."
        )

    db.session.commit()

    return redirect(request.referrer)


@app.route("/finalizar_op/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def finalizar_op(id):
    op = db.session.get(OP, id)
    if not op:
        abort(404)

    tarefas = Tarefa.query.filter_by(op_id=id).all()
    if tarefas and not all(t.validado for t in tarefas):
        return "Ainda existem tarefas pendentes de validação"

    op.status = "FINALIZADA"
    registrar_historico(
        op.id,
        "OP finalizada",
        "OP finalizada."
    )
    db.session.commit()
    return redirect(url_for("ver_op", id=op.id))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") == "development")
