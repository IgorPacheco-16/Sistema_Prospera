# Sistema OP - Gestao de Producao

Sistema web interno em Flask para gerenciamento de Ordens de Producao (OPs), setores, tarefas, prazos, calendario e notificacoes.

## Tecnologias

- Python
- Flask
- Jinja2
- SQLite em desenvolvimento
- SQLAlchemy
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

Variaveis usadas pela aplicacao:

- `SECRET_KEY`: chave secreta do Flask. Use um valor forte em producao.
- `DATABASE_URL`: URL do banco. Se estiver vazia, a aplicacao usa `sqlite:///database.db`.
- `FLASK_ENV`: use `development` localmente para habilitar debug ao rodar `app.py`.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`: configuracoes de envio de email.

O arquivo `.env` nao deve ser versionado.

O projeto tenta carregar `.env` automaticamente quando `python-dotenv` esta instalado. Em deploy, tambem e valido configurar as variaveis diretamente no painel/ambiente do servidor.

## Rodar localmente

Com o ambiente virtual ativo:

```powershell
python app.py
```

Ou usando Flask:

```powershell
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "development"
flask run
```

## SMTP e recuperacao de senha

A recuperacao de senha envia um codigo por email quando as variaveis SMTP estao configuradas:

```text
SMTP_HOST=smtp.exemplo.com
SMTP_PORT=587
SMTP_USER=usuario
SMTP_PASSWORD=senha
SMTP_FROM=sistema@exemplo.com
```

Se SMTP nao estiver configurado, o sistema usa um fallback apenas para desenvolvimento local e mostra o codigo no console. Nao use esse fallback em producao.

## Banco de dados

Por padrao, o desenvolvimento local usa SQLite com `sqlite:///database.db`. Para deploy, configure `DATABASE_URL` conforme o banco do ambiente.

As tabelas sao criadas automaticamente com `db.create_all()` quando a aplicacao inicia.
