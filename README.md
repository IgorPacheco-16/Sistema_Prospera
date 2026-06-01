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
- `MAIL_ENABLED`, `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_DEFAULT_SENDER`: configuracoes de envio de email.
- `EMAILS_OPERACIONAIS_ATIVOS`: habilita disparos operacionais automaticos do sistema quando o SMTP tambem estiver ativo.

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

## Deploy Render + Supabase

No Supabase, crie um projeto PostgreSQL e copie a connection string do banco. Use a URL em formato PostgreSQL em `DATABASE_URL`; se o painel fornecer `postgres://`, a aplicacao converte para `postgresql://` na inicializacao.

No Render, crie um Web Service apontando para este repositorio e configure:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Runtime: Python

O repositório tambem inclui um `Procfile` com:

```text
web: gunicorn app:app
```

Configure as variaveis de ambiente no Render:

- `APP_ENV=production`
- `SECRET_KEY` com um valor forte
- `DATABASE_URL` com a URL PostgreSQL do Supabase
- `MAIL_ENABLED=true`, se envio real de email estiver habilitado
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_DEFAULT_SENDER`, se email estiver habilitado
- `APP_BASE_URL`, recomendado para links absolutos nos emails em producao

Depois do primeiro deploy, abra o Shell do Render e rode:

```bash
flask db upgrade
flask criar-admin
```

Producao inicia com banco virgem e sem seeds. Nao rode `db.create_all()` em producao.

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

A recuperacao de senha, o cadastro por codigo e as notificacoes operacionais usam as variaveis `MAIL_*`. As variaveis antigas `SMTP_*` ainda sao aceitas por compatibilidade local.

Use `MAIL_ENABLED=true` para permitir envio SMTP real. Use `EMAILS_OPERACIONAIS_ATIVOS=true` para liberar emails operacionais gerados por notificacoes, atrasos e futuros relatorios consolidados. As duas condicoes devem estar ativas, com SMTP completo, para disparo real de email operacional.

Em desenvolvimento e testes, mantenha `MAIL_ENABLED=false` ou `EMAILS_OPERACIONAIS_ATIVOS=false` quando nao quiser disparar mensagens reais. Testes devem usar mocks e nunca enviar emails reais.

Se email nao estiver configurado, o sistema usa fallback apenas para desenvolvimento/teste nas notificacoes operacionais e registra erro seguro em producao. Configure email antes do piloto em producao.

Para testar SMTP real sem acionar uma OP ou redefinir senha:

```powershell
flask testar-email --para email@dominio.com
```

## Notificacoes internas

As notificacoes internas podem ser direcionadas por papel (`ADMIN`, `ATENDENTE`, `PCP`, `SETOR`, `ESPECTADOR`) ou por email especifico de usuario. Para usuarios de `SETOR`, notificacoes por papel tambem precisam respeitar `setor_id`; notificacoes por email pertencem ao usuario logado dono daquele email.

Tarefa enviada para validacao deve notificar os validadores: o atendente ativo vinculado a OP, quando encontrado pelo email salvo em `OP.atendente`, e o perfil `PCP`. Responsaveis executores da tarefa nao devem ser o destino principal do evento `tarefa_aguardando_validacao`.

## Relatorios operacionais por email

O digest consolidado ainda nao esta implementado nesta etapa. O desenho recomendado e criar um comando Flask novo, por exemplo:

```powershell
$env:FLASK_APP = "app.py"
flask enviar-relatorio-operacional --janela 10h
flask enviar-relatorio-operacional --janela 15h
```

O comando atual `flask verificar-atrasos --enviar-email` deve ser refatorado para compartilhar consultas e geracao de notificacoes, mas nao deve ser usado como digest final. Ele hoje trabalha por evento e pode gerar multiplos emails separados; o novo comando deve consolidar por destinatario.

Conteudo minimo do relatorio:

- OPs atrasadas.
- Tarefas atrasadas.
- Tarefas proximas do prazo.
- Tarefas aguardando validacao.
- OPs urgentes.
- OPs abertas/criadas recentemente, se ajudar a operacao.
- Pendencias relevantes por papel e permissao.

Agrupamento e permissoes:

- `ATENDENTE`: receber itens das OPs sob sua responsabilidade e pendencias de validacao pertinentes.
- `PCP`: receber visao consolidada de planejamento, atrasos, urgencias e validacoes.
- `SETOR`: receber apenas tarefas e OPs vinculadas ao seu `setor_id`.
- `ADMIN`: pode receber visao ampla se a regra de produto confirmar essa necessidade.
- `ESPECTADOR`: deve ficar fora dos relatorios operacionais.

Para evitar spam, o comando deve enviar no maximo um email por destinatario em cada janela e nao deve disparar quando `MAIL_ENABLED=false`, `EMAILS_OPERACIONAIS_ATIVOS=false` ou SMTP estiver incompleto.

Para evitar duplicidade robusta entre reexecucoes, a proxima etapa deve criar migration com uma tabela propria, por exemplo `notification_email_deliveries`, contendo destinatario, tipo do relatorio, janela (`10h` ou `15h`), data operacional em `America/Sao_Paulo`, hash/conteudo resumido, status, erro seguro e timestamps. Sem essa tabela, o sistema fica dependente apenas de logs/processo e nao consegue garantir idempotencia em retries.

Agendamento no Render:

- Criar dois Cron Jobs apontando para o mesmo ambiente do Web Service.
- Usar `flask db upgrade` no deploy normal antes dos cron jobs.
- Rodar `flask enviar-relatorio-operacional --janela 10h` as 13:00 UTC.
- Rodar `flask enviar-relatorio-operacional --janela 15h` as 18:00 UTC.

Timezone: o produto deve considerar `America/Sao_Paulo`. Em 2026-06-01, a conversao validada foi 10:00 Sao Paulo = 13:00 UTC e 15:00 Sao Paulo = 18:00 UTC. Como o Brasil normalmente opera em UTC-3, esses horarios devem ser revisados se houver mudanca legal de fuso ou horario de verao.
