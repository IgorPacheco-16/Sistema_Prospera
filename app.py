import click
from flask import Flask, g, request, session
from flask_migrate import Migrate
from database.models import db, Notificacao, User
from tempo import formatar_data_hora_brasilia
import importlib.util
import os
import time
from pathlib import Path
from werkzeug.security import generate_password_hash

from email_service import enviar_email

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
tarefas_routes_module = carregar_modulo("pacheco_tarefas_routes", "app/tarefas/routes.py")
kanban_routes_module = carregar_modulo("pacheco_kanban_routes", "app/kanban/routes.py")
metricas_routes_module = carregar_modulo("pacheco_metricas_routes", "app/metricas/routes.py")
slides_routes_module = carregar_modulo("pacheco_slides_routes", "app/slides/routes.py")

configure_app = config_module.configure_app
initialize_database = config_module.initialize_database

is_admin = security_module.is_admin
is_atendente = security_module.is_atendente
is_setor = security_module.is_setor
usuario_pode_acionar_tarefa = security_module.usuario_pode_acionar_tarefa
login_required = security_module.login_required
tipos_permitidos = security_module.tipos_permitidos
normalizar_email = security_module.normalizar_email
gerar_codigo_recuperacao = security_module.gerar_codigo_recuperacao
enviar_email_recuperacao = security_module.enviar_email_recuperacao
enviar_email_cadastro = security_module.enviar_email_cadastro

registrar_historico = historico_module.registrar_historico

link_op = notificacoes_module.link_op
link_tarefa = notificacoes_module.link_tarefa
query_notificacoes_usuario = notificacoes_module.query_notificacoes_usuario
criar_notificacao = notificacoes_module.criar_notificacao
enviar_email_operacional = notificacoes_module.enviar_email_operacional
gerar_notificacoes_pendentes = notificacoes_module.gerar_notificacoes_pendentes
verificar_atrasos = notificacoes_module.verificar_atrasos
mensagem_op = notificacoes_module.mensagem_op
mensagem_tarefa = notificacoes_module.mensagem_tarefa
categoria_notificacao = notificacoes_module.categoria_notificacao
create_notificacoes_blueprint = notificacoes_routes_module.create_notificacoes_blueprint
create_auth_blueprint = auth_routes_module.create_auth_blueprint
create_usuarios_blueprint = usuarios_routes_module.create_usuarios_blueprint
create_dashboard_blueprint = dashboard_routes_module.create_dashboard_blueprint
create_calendario_blueprint = calendario_routes_module.create_calendario_blueprint
create_ops_blueprint = ops_routes_module.create_ops_blueprint
create_tarefas_blueprint = tarefas_routes_module.create_tarefas_blueprint
create_kanban_blueprint = kanban_routes_module.create_kanban_blueprint
create_metricas_blueprint = metricas_routes_module.create_metricas_blueprint
create_slides_blueprint = slides_routes_module.create_slides_blueprint


BUILD_ONLY_ALIASES = [
    ("/", "login"),
    ("/logout", "logout"),
    ("/esqueci_senha", "esqueci_senha"),
    ("/redefinir_senha", "redefinir_senha"),
    ("/definir_senha", "definir_senha"),
    ("/criar_conta", "criar_conta"),
    ("/criar_conta/codigo", "validar_codigo_cadastro"),
    ("/criar_conta/finalizar", "finalizar_cadastro"),
    ("/criar_usuario", "criar_usuario"),
    ("/usuarios", "listar_usuarios"),
    ("/usuarios/<int:id>/editar", "editar_usuario"),
    ("/usuarios/<int:id>/alternar_status", "alternar_status_usuario"),
    ("/usuarios/<int:id>/excluir", "excluir_usuario"),
    ("/minha_conta", "minha_conta"),
    ("/notificacoes", "notificacoes"),
    ("/ler_notificacao/<int:id>", "ler_notificacao"),
    ("/api/notificacoes", "api_notificacoes"),
    ("/teste_notificacao", "teste_notificacao"),
    ("/dashboard", "dashboard"),
    ("/calendario", "calendario"),
    ("/kanban", "kanban"),
    ("/metricas", "metricas"),
    ("/slides", "slides"),
    ("/api/slides", "api_slides"),
    ("/arquivadas", "arquivadas"),
    ("/criar_op", "criar_op"),
    ("/op/<int:id>", "ver_op"),
    ("/editar_op/<int:id>", "editar_op"),
    ("/arquivar_op/<int:id>", "arquivar_op"),
    ("/desarquivar_op/<int:id>", "desarquivar_op"),
    ("/excluir_op/<int:id>", "excluir_op"),
    ("/finalizar_op/<int:id>", "finalizar_op"),
    ("/criar_tarefa/<int:op_id>/<int:setor_id>", "criar_tarefa"),
    ("/iniciar_tarefa/<int:id>", "iniciar_tarefa"),
    ("/entregar_tarefa/<int:id>", "entregar_tarefa"),
    ("/validar_tarefa/<int:id>", "validar_tarefa"),
    ("/recusar_tarefa/<int:id>", "recusar_tarefa"),
    ("/editar_tarefa/<int:id>", "editar_tarefa"),
    ("/excluir_tarefa/<int:id>", "excluir_tarefa"),
]


def registrar_aliases_build_only(app):
    for rule, endpoint in BUILD_ONLY_ALIASES:
        app.add_url_rule(rule, endpoint=endpoint, build_only=True)


app = Flask(__name__)
configure_app(app)
db.init_app(app)
Migrate(app, db)
app.jinja_env.filters["data_hora_brasilia"] = formatar_data_hora_brasilia
app.jinja_env.filters["categoria_notificacao"] = categoria_notificacao

initialize_database(app)

auth_bp = create_auth_blueprint(
    login_required=login_required,
    normalizar_email=normalizar_email,
    gerar_codigo_recuperacao=gerar_codigo_recuperacao,
    enviar_email_recuperacao=enviar_email_recuperacao,
    enviar_email_cadastro=enviar_email_cadastro
)
app.register_blueprint(auth_bp)

usuarios_bp = create_usuarios_blueprint(
    login_required=login_required,
    tipos_permitidos=tipos_permitidos,
    normalizar_email=normalizar_email
)
app.register_blueprint(usuarios_bp)

notificacoes_bp = create_notificacoes_blueprint(
    login_required=login_required,
    is_setor=is_setor,
    gerar_notificacoes_pendentes=gerar_notificacoes_pendentes,
    query_notificacoes_usuario=query_notificacoes_usuario,
    criar_notificacao=criar_notificacao,
    categoria_notificacao=categoria_notificacao
)
app.register_blueprint(notificacoes_bp)

dashboard_bp = create_dashboard_blueprint(
    login_required=login_required,
    gerar_notificacoes_pendentes=gerar_notificacoes_pendentes
)
app.register_blueprint(dashboard_bp)

calendario_bp = create_calendario_blueprint(login_required=login_required)
app.register_blueprint(calendario_bp)

kanban_bp = create_kanban_blueprint(login_required=login_required)
app.register_blueprint(kanban_bp)

metricas_bp = create_metricas_blueprint(tipos_permitidos=tipos_permitidos)
app.register_blueprint(metricas_bp)

ops_bp = create_ops_blueprint(
    login_required=login_required,
    tipos_permitidos=tipos_permitidos,
    is_admin=is_admin,
    is_atendente=is_atendente,
    usuario_pode_acionar_tarefa=usuario_pode_acionar_tarefa,
    criar_notificacao=criar_notificacao,
    mensagem_op=mensagem_op,
    link_op=link_op,
    enviar_email_operacional=enviar_email_operacional,
    registrar_historico=registrar_historico
)
app.register_blueprint(ops_bp)

tarefas_bp = create_tarefas_blueprint(
    tipos_permitidos=tipos_permitidos,
    is_setor=is_setor,
    usuario_pode_acionar_tarefa=usuario_pode_acionar_tarefa,
    criar_notificacao=criar_notificacao,
    mensagem_tarefa=mensagem_tarefa,
    link_tarefa=link_tarefa,
    enviar_email_operacional=enviar_email_operacional,
    registrar_historico=registrar_historico
)
app.register_blueprint(tarefas_bp)

slides_bp = create_slides_blueprint(tipos_permitidos=tipos_permitidos)
app.register_blueprint(slides_bp)

registrar_aliases_build_only(app)


if config_module.app_env() in {"development", "test"}:
    @app.before_request
    def iniciar_medicao_requisicao():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def registrar_tempo_requisicao(response):
        inicio = getattr(g, "request_started_at", None)
        if inicio is not None:
            duracao_ms = (time.perf_counter() - inicio) * 1000
            app.logger.debug(
                "request_timing path=%s endpoint=%s status=%s duration_ms=%.1f",
                request.path,
                request.endpoint,
                response.status_code,
                duracao_ms
            )
        return response


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

    return {}


@app.cli.command("criar-admin")
@click.option("--email", prompt="Email")
@click.option("--nome", prompt="Nome")
@click.option(
    "--senha",
    prompt="Senha",
    hide_input=True,
    confirmation_prompt=True
)
def criar_admin(email, nome, senha):
    email_normalizado = normalizar_email(email)
    nome = (nome or "").strip()
    senha = senha or ""

    if not email_normalizado:
        raise click.ClickException("Informe um email valido.")

    if not nome:
        raise click.ClickException("Informe o nome do administrador.")

    if not senha.strip():
        raise click.ClickException("Informe uma senha.")

    admin_ativo = User.query.filter_by(tipo="ADMIN", ativo=True).first()
    if admin_ativo:
        raise click.ClickException(
            "Ja existe um administrador ativo. Use a gestao de usuarios."
        )

    if User.query.filter_by(email=email_normalizado).first():
        raise click.ClickException("Ja existe um usuario com este email.")

    db.session.add(User(
        email=email_normalizado,
        nome=nome,
        senha=generate_password_hash(senha),
        tipo="ADMIN",
        ativo=True
    ))
    db.session.commit()
    click.echo(f"Administrador criado: {email_normalizado}")


@app.cli.command("testar-email")
@click.option("--para", required=True, help="Email destinatario do teste.")
def testar_email(para):
    destinatario = normalizar_email(para)
    if not destinatario:
        raise click.ClickException("Informe um email valido em --para.")

    resultado = enviar_email(
        [destinatario],
        "Teste de email - Sistema OP",
        (
            "Este e um teste controlado de envio SMTP do Sistema OP.\n\n"
            "Se voce recebeu esta mensagem, a configuracao de email esta funcionando."
        ),
    )
    if not resultado.enviado:
        raise click.ClickException(resultado.erro or "Email nao enviado.")

    click.echo(f"Email de teste enviado para {destinatario}.")


@app.cli.command("verificar-atrasos")
@click.option(
    "--enviar-email",
    is_flag=True,
    help="Tenta enviar emails operacionais pendentes de atraso.",
)
def verificar_atrasos_cli(enviar_email):
    resumo = verificar_atrasos(enviar_emails=enviar_email)
    db.session.commit()

    click.echo("Verificacao de atrasos concluida.")
    click.echo(f"Tarefas atrasadas: {resumo['tarefas_atrasadas']}")
    click.echo(f"OPs atrasadas: {resumo['ops_atrasadas']}")
    click.echo(f"OPs urgentes: {resumo['ops_urgentes']}")
    click.echo(f"Notificacoes criadas: {resumo['notificacoes_criadas']}")
    click.echo(
        "Emails de tarefas atrasadas enviados: "
        f"{resumo['emails_tarefa_atrasada_enviados']}"
    )
    if not enviar_email:
        click.echo("Emails nao foram enviados. Use --enviar-email para disparar.")


if __name__ == "__main__":
    app.run(debug=os.environ.get("APP_ENV") == "development")
