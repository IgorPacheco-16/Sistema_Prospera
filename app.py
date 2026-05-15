from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify, flash
from database.models import db, User, OP, Tarefa, Notificacao, Setor, OPSetor
from datetime import datetime, timedelta, date
from functools import wraps
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'segredo123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db.init_app(app)

#Permissões internas para cada setor (Permite que apenas alguns setores possam acessar algumas opções e sejam barrados)

def is_admin(): return session.get("tipo") == "ADMIN"
def is_atendente(): return session.get("tipo") == "ATENDENTE"
def is_pcp(): return session.get("tipo") == "PCP"
def is_setor(): return session.get("tipo") == "SETOR"

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

def tipos_permitidos(*tipos):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("login"))

            if session.get("tipo") not in tipos:
                return "Acesso negado", 403

            return func(*args, **kwargs)
        return wrapper
    return decorator

#Init do banco de dados

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

with app.app_context():
    db.create_all()
    garantir_coluna_alta_prioridade()

    setores_nomes = [
        "Atendimento","Criação","Projeto","Compras/Estoque","PCP",
        "Arte Final","Pré-impressão","Impressão","Marcenaria",
        "Acabamento","Terceirização","Expedição","Operacional"
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
        email = f"{setor.nome.lower().replace(' ', '').replace('/', '').replace('-', '')}@teste.com"
        if not User.query.filter_by(email=email).first():
            db.session.add(User(
                email=email,
                senha=generate_password_hash("123"),
                tipo="SETOR",
                setor_id=setor.id,
                ativo=True
            ))

    db.session.commit()

#Função para os logins

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.senha, senha):
            session["usuario"] = user.email
            session["tipo"] = user.tipo
            session["setor_id"] = user.setor_id
            return redirect(url_for("dashboard"))

        return render_template("auth/login.html", erro="Email ou senha inválidos")

    return render_template("auth/login.html")

#Função para o logout

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

#Função para as notificações (ainda em desenvolvimento)

def verificar_atrasos():
    hoje = date.today()
    tarefas = Tarefa.query.all()

    for t in tarefas:
        if t.prazo and t.prazo < hoje and not t.validado:
            op = db.session.get(OP, t.op_id)
            mensagem = f"{t.setor.nome} atrasado na OP '{op.nome}'"

            existe = Notificacao.query.filter_by(
                usuario="ATENDENTE",
                mensagem=mensagem
            ).first()

            if not existe:
                db.session.add(Notificacao(
                    usuario="ATENDENTE",
                    mensagem=mensagem
                ))

    db.session.commit()

@app.before_request
def before():
    if "usuario" in session:
        verificar_atrasos()

@app.context_processor
def inject_notificacoes():
    if "tipo" in session:
        notificacoes = Notificacao.query.filter_by(
            usuario=session.get("tipo"),
            lida=False
        ).all()

        return dict(
            total_notificacoes=len(notificacoes)
        )

    return dict(total_notificacoes=0)

@app.route("/notificacoes")
@login_required
def notificacoes():
    lista = Notificacao.query.filter_by(
        usuario=session.get("tipo"),
        lida=False
    ).all()

    return render_template("notificacoes/index.html", notificacoes=lista)

@app.route("/ler_notificacao/<int:id>", methods=["POST"])
@login_required
def ler_notificacao(id):
    notif = Notificacao.query.get_or_404(id)

    if notif.usuario != session.get("tipo"):
        return "Acesso negado", 403

    notif.lida = True
    db.session.commit()
    return redirect(url_for("notificacoes"))

#Rota para a importação do Dashboard (pág inicial do sistema) e também o core do projeto

from datetime import date, datetime

@app.route("/dashboard")
@login_required
def dashboard():
    hoje = date.today()

    busca = request.args.get("busca", "")
    status = request.args.get("status", "")
    atrasadas_filtro = request.args.get("atrasadas", "")
    filtro_ativo = bool(busca or status or atrasadas_filtro)

    query = OP.query.filter(OP.status != "ARQUIVADA")

    if busca:
        query = query.filter(OP.nome.ilike(f"%{busca}%"))

    ops_base = query.all()

    total = len(ops_base)
    atrasadas = sum(
        1 for op in ops_base
        if op.prazo_final and op.prazo_final < hoje and op.status != "FINALIZADA"
    )
    em_andamento = sum(1 for op in ops_base if op.status == "EM ANDAMENTO")
    finalizadas = sum(1 for op in ops_base if op.status == "FINALIZADA")

    if status:
        ops = [op for op in ops_base if op.status == status]
    else:
        ops = [op for op in ops_base if op.status != "FINALIZADA"]

    lista_ops = []

    for op in ops:
        tarefas = Tarefa.query.filter_by(op_id=op.id).all()

        total_tarefas = len(tarefas)
        validadas = sum(1 for t in tarefas if t.validado)

        #Se tiver algum tipo de atraso, aqui aplicamos as cores
        if op.status == "FINALIZADA":
            cor = "finalizada"
        elif op.prazo_final and op.prazo_final < hoje:
            cor = "vermelho"
        elif op.prazo_final and (op.prazo_final - hoje).days <= 2:
            cor = "laranja"
        elif op.prazo_final and (op.prazo_final - hoje).days <= 5:
            cor = "amarelo"
        else:
            cor = "verde"

        lista_ops.append({
            "op": op,
            "cor": cor,
            "total_tarefas": total_tarefas,
            "validadas": validadas
        })

    #Filtro para só atrasadas
    if atrasadas_filtro:
        lista_ops = [
            item for item in lista_ops
            if item["op"].prazo_final
            and item["op"].prazo_final < hoje
            and item["op"].status != "FINALIZADA"
        ]

    #Ordem para aparecer no dash: prioridade > atraso > prazo
    lista_ops.sort(
        key=lambda x: (
            not getattr(x["op"], "alta_prioridade", False),
            x["op"].status == "FINALIZADA",
            x["op"].prazo_final is None,
            x["op"].prazo_final or datetime.max.date()
        )
    )

    return render_template(
        "dashboard/index.html",
        usuario=session.get("usuario"),
        tipo=session.get("tipo"),
        ops=lista_ops,
        total=total,
        atrasadas=atrasadas,
        em_andamento=em_andamento,
        finalizadas=finalizadas,
        busca=busca,
        status=status,
        filtro_ativo=filtro_ativo,
        atrasadas_filtro=bool(atrasadas_filtro)
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

    return render_template(
        "op/detalhe.html",
        op=op,
        estrutura=estrutura,
        setores=Setor.query.all(),
        tipo=session.get("tipo"),
        today=date.today()
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
    db.session.delete(op)
    db.session.commit()

    return redirect(url_for("dashboard"))

#Ops que forem arquivadas recebem o status de arquivadas

@app.route("/arquivadas")
@login_required
def arquivadas():
    ops = OP.query.filter_by(status="ARQUIVADA").all()
    return render_template("arquivadas/index.html", ops=ops)

@app.route("/desarquivar_op/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def desarquivar_op(id):
    op = db.session.get(OP, id)
    if not op:
        abort(404)

    op.status = "EM ANDAMENTO"
    db.session.commit()
    return redirect(url_for("arquivadas"))

#Rota para entrarmos no calendário com a lógica por traás

@app.route("/calendario")
@login_required
def calendario():
    hoje = date.today()
    amanha = hoje + timedelta(days=1)
    semana = hoje + timedelta(days=7)
    mes = hoje + timedelta(days=30)

    tarefas = Tarefa.query.all()

    hoje_amanha = []
    semana_lista = []
    mes_lista = []

    for t in tarefas:
        if t.prazo and not t.validado:
            op = db.session.get(OP, t.op_id)

            if t.prazo <= amanha:
                hoje_amanha.append((t, op))
            elif t.prazo <= semana:
                semana_lista.append((t, op))
            elif t.prazo <= mes:
                mes_lista.append((t, op))

    return render_template(
        "calendario/index.html",
        hoje_amanha=hoje_amanha,
        semana=semana_lista,
        mes=mes_lista,
        today=hoje
    )

#Rota para criar um novo usuário (preciso atualizar isso)

@app.route("/criar_usuario", methods=["GET", "POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def criar_usuario():
    setores = Setor.query.all()

    if request.method == "POST":
        email = request.form.get("email")
        tipo = request.form.get("tipo")
        setor_id = request.form.get("setor")

        novo_usuario = User(
            email=email,
            tipo=tipo,
            setor_id=int(setor_id) if setor_id else None,
            senha=None,
            ativo=False
        )

        db.session.add(novo_usuario)
        db.session.commit()

        return "Usuário criado! Ele precisa ativar a conta."

    return render_template("usuario/criar_usuario.html", setores=setores)


#Rota para definir a senha do usuário na sua primeira vez logando (preciso mexer nisso)

@app.route("/definir_senha", methods=["GET", "POST"])
def definir_senha():
    if "tmp_user" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["tmp_user"])

    if request.method == "POST":
        senha = request.form.get("senha")

        user.senha = generate_password_hash(senha)
        user.ativo = True

        db.session.commit()

        session.pop("tmp_user")

        return redirect(url_for("login"))

    return render_template("auth/definir_senha.html")


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
            db.session.add(OPSetor(
                op_id=op.id,
                setor_id=setor_id
            ))

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
                db.session.delete(op_setor)

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

    tarefa.nome = request.form.get("nome")

    prazo = request.form.get("prazo")
    if prazo:
        tarefa.prazo = datetime.strptime(prazo, "%Y-%m-%d").date()
    else:
        tarefa.prazo = None

    db.session.commit()
    return redirect(request.referrer)


@app.route("/excluir_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("PCP", "ATENDENTE", "ADMIN")
def excluir_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)
    op_id = tarefa.op_id

    db.session.delete(tarefa)
    db.session.commit()

    return redirect(url_for("ver_op", id=op_id))

@app.route("/recusar_tarefa/<int:id>", methods=["POST"])
@tipos_permitidos("ATENDENTE", "ADMIN")
def recusar_tarefa(id):
    tarefa = Tarefa.query.get_or_404(id)
    tarefa.entregue = False
    tarefa.validado = False
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
    db.session.commit()
    return redirect(url_for("ver_op", id=op.id))


#Core para a criação de notificações (Ainda está com a lógica antiga, preciso mexer nisso)

@app.route("/api/notificacoes")
@login_required
def api_notificacoes():
    total = Notificacao.query.filter_by(
        usuario=session.get("tipo"),
        lida=False
    ).count()

    return jsonify({"total": total})


#Teste para ver se a notificação está funcionando...

@app.route("/teste_notificacao")
@login_required
def teste_notificacao():
    notif = Notificacao(
        usuario=session.get("tipo"),
        mensagem="🚨 Teste funcionando!"
    )

    db.session.add(notif)
    db.session.commit()

    return "OK"

if __name__ == "__main__":
    app.run(debug=True)
