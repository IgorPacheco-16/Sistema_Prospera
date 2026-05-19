# Sistema OP - Gestao de Producao

Sistema web interno em Flask para gerenciamento de Ordens de Producao (OPs), setores, tarefas, prazos, calendario e notificacoes.

## Tecnologias

- Python
- Flask
- Jinja2
- SQLite em desenvolvimento e teste
- PostgreSQL em producao
- SQLAlchemy
- Flask-Migrate
- Bootstrap
- CSS proprio em `static/css/theme.css`

## Instalar

Crie e ative um ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependencias:

```powershell
python -m pip install -r requirements.txt
```

## Configurar ambiente

Copie `.env.example` para `.env` e preencha os valores conforme o ambiente:

```powershell
Copy-Item .env.example .env
```

Variaveis principais:

- `APP_ENV`: ambiente atual. Use `development`, `test` ou `production`.
- `SECRET_KEY`: chave secreta do Flask. Obrigatoria fora de desenvolvimento.
- `DATABASE_URL`: URL do banco.
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS`, `MAIL_DEFAULT_SENDER`: configuracoes de envio de email.

Em `APP_ENV=production`, `DATABASE_URL` e obrigatoria e deve apontar para PostgreSQL. URLs iniciadas com `postgres://` sao convertidas para `postgresql://`.

Em `APP_ENV=test`, a aplicacao usa SQLite de teste. Em `APP_ENV=development`, se `DATABASE_URL` estiver vazia, a aplicacao usa SQLite local com `sqlite:///database.db`.

O arquivo `.env` nao deve ser versionado.

## Banco de dados

O projeto usa migracoes do Flask-Migrate. Depois de configurar o ambiente e o banco, rode:

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
```

Nao use `db.create_all()` para preparar o banco da aplicacao. O fluxo esperado e sempre aplicar as migracoes com `flask db upgrade`.

Em producao, o sistema inicia com banco virgem e sem seeds. Depois das migracoes, crie o primeiro administrador:

```powershell
flask criar-admin
```

## Rodar localmente

Com o ambiente virtual ativo:

```powershell
python app.py
```

Ou usando Flask:

```powershell
$env:FLASK_APP = "app.py"
$env:APP_ENV = "development"
flask run
```

## Testes

Rode a suite com:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## Email

A recuperacao de senha e as notificacoes operacionais usam as variaveis `MAIL_*`. As variaveis antigas `SMTP_*` ainda sao aceitas por compatibilidade local.

Se email nao estiver configurado, o sistema usa fallback apenas para desenvolvimento/teste e registra a mensagem no console. Configure email antes do piloto em producao.
