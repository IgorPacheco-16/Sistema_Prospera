# Preparacao para Google Cloud Run

Este documento prepara o Sistema Prospera para rodar em container no Google Cloud Run, em paralelo ao Render atual. Ele nao executa deploy, nao altera banco remoto e nao substitui o fluxo atual de producao.

## Arquitetura paralela

- Render continua servindo a producao atual com `gunicorn app:app`.
- Cloud Run sera um ambiente paralelo na regiao `southamerica-east1`.
- Supabase continua sendo o banco PostgreSQL. Nao ha migracao de banco nesta etapa.
- As variaveis e secrets devem ser configuradas separadamente no Cloud Run.
- O trafego so deve ser direcionado para Cloud Run depois de validacao funcional e comparacao com Render.

## Container

O `Dockerfile` usa `python:3.13.12-slim`, alinhado ao `runtime.txt` atual. O processo inicia com Gunicorn, escutando em `0.0.0.0` e respeitando a variavel `PORT` fornecida pelo Cloud Run:

```text
gunicorn --bind 0.0.0.0:${PORT:-8080} --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-120} app:app
```

A configuracao inicial usa 1 worker por container porque o sistema possui cache em memoria por processo, especialmente em `/api/slides`. `threads=4` permite concorrencia moderada sem criar caches independentes dentro do mesmo container. `timeout=120` preserva uma margem conservadora para rotas mais pesadas enquanto a migracao para Cloud Run e medida.

O container nao executa `flask db upgrade`, seeds, criacao de usuario ou servidor de desenvolvimento Flask no `CMD`.

## Build local

```powershell
docker build -t sistema-prospera-cloud-run .
```

## Execucao local do container

Use um arquivo local de ambiente que nao seja versionado. Nao grave secrets reais no repositorio.

```powershell
docker run --rm -p 8080:8080 --env-file .env.local sistema-prospera-cloud-run
```

Para um teste local sem banco remoto, use `APP_ENV=development` ou `APP_ENV=local` e uma `DATABASE_URL` local adequada. Para simular producao, use `APP_ENV=production`, `SECRET_KEY` forte e `DATABASE_URL` PostgreSQL valida.

## Health checks

`GET /health` retorna apenas:

```json
{"status":"ok"}
```

Ele nao executa query de banco e pode ser usado como health check de container.

`GET /db-health` executa `SELECT 1` e retorna latencia total em `elapsed_ms`. Use esse endpoint para comparar a latencia Cloud Run + Supabase contra Render + Supabase. Se `elapsed_ms` estiver alto logo apos subir uma revisao, repetir a medicao ajuda a separar cold start, conexao inicial e latencia SQL real.

## Comandos conceituais de Cloud Run

Os comandos abaixo sao exemplos. Ajuste projeto, imagem, service account e secrets antes de usar.

```powershell
gcloud config set run/region southamerica-east1
gcloud builds submit --tag southamerica-east1-docker.pkg.dev/PROJECT_ID/prospera/sistema-prospera:REVISAO
gcloud run deploy sistema-prospera `
  --image southamerica-east1-docker.pkg.dev/PROJECT_ID/prospera/sistema-prospera:REVISAO `
  --region southamerica-east1 `
  --platform managed `
  --allow-unauthenticated `
  --set-env-vars APP_ENV=production,MAIL_ENABLED=false,EMAILS_OPERACIONAIS_ATIVOS=false `
  --set-secrets SECRET_KEY=prospera-secret-key:latest,DATABASE_URL=prospera-database-url:latest
```

Nao execute esses comandos nesta etapa sem uma decisao explicita de deploy.

## Inventario de variaveis

| Variavel | Obrigatoria | Sensivel | Uso | Valor de exemplo seguro | Classificacao |
| --- | --- | --- | --- | --- | --- |
| `APP_ENV` | Sim no Cloud Run | Nao | Define ambiente. Em `production`, exige PostgreSQL e `SECRET_KEY`. | `production` | Comum; necessaria no Cloud Run |
| `DATABASE_URL` | Sim em `production` | Sim | URL SQLAlchemy do banco. Em producao deve ser PostgreSQL. | `postgresql://usuario:senha@host:5432/banco` | Secret; necessaria no Cloud Run |
| `SECRET_KEY` | Sim em `production` | Sim | Chave de sessao/assinatura Flask. | `gerado-no-secret-manager` | Secret; necessaria no Cloud Run |
| `PORT` | Sim no Cloud Run | Nao | Porta injetada pelo Cloud Run e usada pelo Gunicorn. | `8080` | Comum; necessaria no Cloud Run |
| `APP_BASE_URL` | Recomendado em producao | Nao | Base para links absolutos em emails operacionais. | `https://sistema-prospera-xyz.a.run.app` | Comum; necessaria se emails usarem links |
| `SLOW_REQUEST_MS` | Nao | Nao | Limite para log de requests lentas. Padrao: `1000`. | `1000` | Opcional |
| `SLIDES_CACHE_TTL_SECONDS` | Nao | Nao | TTL do cache em memoria de `/api/slides`. Padrao: `60`. | `60` | Opcional |
| `NOTIFICACOES_INTERVALO_SEGUNDOS` | Nao | Nao | Intervalo minimo entre geracoes de notificacoes pendentes. Padrao: `300`, exceto testes. | `300` | Opcional |
| `MAIL_ENABLED` | Nao | Nao | Liga/desliga envio SMTP geral. | `false` | Comum; necessaria se email real for usado |
| `MAIL_SERVER` | Se `MAIL_ENABLED=true` | Nao | Host SMTP. | `smtp.example.com` | Comum; necessaria se email real for usado |
| `MAIL_PORT` | Se `MAIL_ENABLED=true` | Nao | Porta SMTP. | `587` | Comum; necessaria se email real for usado |
| `MAIL_USERNAME` | Se `MAIL_ENABLED=true` | Sim | Usuario SMTP. | `usuario@example.com` | Secret; necessaria se email real for usado |
| `MAIL_PASSWORD` | Se `MAIL_ENABLED=true` | Sim | Senha ou token SMTP. | `armazenado-no-secret-manager` | Secret; necessaria se email real for usado |
| `MAIL_DEFAULT_SENDER` | Se `MAIL_ENABLED=true` | Nao | Remetente padrao. | `sistema@example.com` | Comum; necessaria se email real for usado |
| `MAIL_USE_TLS` | Nao | Nao | Habilita STARTTLS. Padrao: `true`, salvo SSL ativo. | `true` | Opcional |
| `MAIL_USE_SSL` | Nao | Nao | Habilita SMTP SSL direto. Padrao: `false`. | `false` | Opcional |
| `EMAILS_OPERACIONAIS_ATIVOS` | Nao | Nao | Libera emails operacionais e relatorio consolidado. | `false` | Comum; necessaria se email operacional real for usado |
| `ENVIAR_EMAILS_OPERACIONAIS` | Nao | Nao | Alias legado de `EMAILS_OPERACIONAIS_ATIVOS`. | `false` | Opcional; compatibilidade |
| `AMBIENTE` | Nao | Nao | Trava adicional para CLI de seed de usuarios teste. | `production` | Opcional; seguranca operacional |
| `GUNICORN_WORKERS` | Nao | Nao | Sobrescreve workers do container. Padrao: `1`. | `1` | Opcional; Cloud Run |
| `GUNICORN_THREADS` | Nao | Nao | Sobrescreve threads do Gunicorn. Padrao: `4`. | `4` | Opcional; Cloud Run |
| `GUNICORN_TIMEOUT` | Nao | Nao | Sobrescreve timeout do Gunicorn. Padrao: `120`. | `120` | Opcional; Cloud Run |
| `EMAIL_ENABLED` | Nao | Nao | Alias aceito para `MAIL_ENABLED`. | `false` | Opcional; compatibilidade |
| `SMTP_ENABLED` | Nao | Nao | Alias aceito para `MAIL_ENABLED`. | `false` | Opcional; compatibilidade |
| `SMTP_HOST` / `SMTP_SERVER` / `EMAIL_HOST` / `EMAIL_SERVER` | Nao | Nao | Aliases aceitos para `MAIL_SERVER`. | `smtp.example.com` | Opcional; compatibilidade |
| `SMTP_PORT` / `EMAIL_PORT` | Nao | Nao | Aliases aceitos para `MAIL_PORT`. | `587` | Opcional; compatibilidade |
| `SMTP_USER` / `SMTP_USERNAME` / `EMAIL_USER` / `EMAIL_USERNAME` | Nao | Sim | Aliases aceitos para `MAIL_USERNAME`. | `usuario@example.com` | Secret opcional; compatibilidade |
| `SMTP_PASSWORD` / `SMTP_PASS` / `EMAIL_PASSWORD` | Nao | Sim | Aliases aceitos para `MAIL_PASSWORD`. | `armazenado-no-secret-manager` | Secret opcional; compatibilidade |
| `SMTP_FROM` / `EMAIL_FROM` / `DEFAULT_FROM_EMAIL` | Nao | Nao | Aliases aceitos para `MAIL_DEFAULT_SENDER`. | `sistema@example.com` | Opcional; compatibilidade |
| `SMTP_USE_TLS` / `EMAIL_USE_TLS` | Nao | Nao | Aliases aceitos para `MAIL_USE_TLS`. | `true` | Opcional; compatibilidade |
| `SMTP_USE_SSL` / `EMAIL_USE_SSL` | Nao | Nao | Aliases aceitos para `MAIL_USE_SSL`. | `false` | Opcional; compatibilidade |

Nao foi encontrada variavel especifica do Render no codigo. O valor de `APP_BASE_URL` pode apontar para Render ou Cloud Run conforme o ambiente.

## Secrets no Cloud Run

Trate como secrets:

- `DATABASE_URL`
- `SECRET_KEY`
- `MAIL_USERNAME`, se usado
- `MAIL_PASSWORD`, se usado
- aliases SMTP/EMAIL equivalentes que contenham usuario ou senha

Preferir Secret Manager e `--set-secrets` em vez de `--set-env-vars` para esses valores.

## Estrategia de migrations

- Migrations nao devem rodar no startup do container.
- O `CMD` do container nao executa `flask db upgrade`.
- Antes de um deploy real, confirmar se o banco Supabase ja esta no head esperado.
- Para esta primeira implantacao paralela, se o banco ja estiver atualizado, nao executar nada.
- O head local observado nesta preparacao foi `6a8b9c0d1e2f (head)`.
- Quando houver migration futura, executar como etapa controlada e auditavel antes do deploy que depende dela.

Comando conceitual para uma etapa controlada futura:

```powershell
$env:FLASK_APP = "app.py"
$env:APP_ENV = "production"
flask db current
flask db upgrade
flask db current
```

Nao execute em banco remoto sem janela operacional, backup/rollback planejado e confirmacao explicita.

## Compatibilidade com Cloud Run

Pontos verificados:

- Nao ha comando automatico de migration, seed ou criacao de usuario no startup de producao.
- `initialize_database(app)` so executa `db.create_all()` e seeds quando `APP_ENV=test`.
- Em `APP_ENV=production`, SQLite e `DATABASE_URL` ausente sao bloqueados.
- O app carrega `.env` ou `shounen.env` se esses arquivos existirem. A imagem ignora esses arquivos; no Cloud Run use variaveis/secrets da plataforma.
- `/api/slides` usa cache em memoria por processo. Por isso o container inicia com `workers=1`.
- Ha estado em memoria para intervalo de geracao de notificacoes pendentes (`_ultima_geracao_pendentes`). Em Cloud Run, esse estado e por instancia e nao deve ser tratado como coordenacao global.
- Nao foi encontrado uso de uploads locais ou escrita persistente de arquivos pelo fluxo principal.
- `OP.caminho_pasta` armazena caminho informado pelo usuario e aparece no front-end, mas o servidor nao acessa esse caminho.
- Bancos SQLite locais ficam em `instance/` e nao entram na imagem.
- Nao foi encontrado scheduler interno Python. Os jobs de relatorio devem ser externos/controlados, como Cloud Scheduler ou Cloud Run Jobs.
- Templates, static e migrations precisam entrar na imagem e nao estao ignorados pelo `.dockerignore`.

## Comparar Render e Cloud Run

1. Abrir `/health` nos dois ambientes.
2. Abrir `/db-health` nos dois ambientes apos aquecimento e comparar `elapsed_ms`.
3. Validar login, dashboard, kanban, calendario, metricas, notificacoes e slides.
4. Comparar logs de request lenta sem expor SQL, payloads ou secrets.
5. Manter `MAIL_ENABLED=false` e `EMAILS_OPERACIONAIS_ATIVOS=false` no primeiro smoke test, salvo decisao explicita.
6. So trocar trafego quando a versao Cloud Run estiver funcionalmente equivalente.

## Rollback

- Render permanece como ambiente principal durante a preparacao.
- Se Cloud Run falhar, pare de direcionar testes/trafego para a revisao Cloud Run e mantenha Render.
- No Cloud Run, use revisoes: voltar para uma revisao anterior ou zerar trafego da revisao com problema.
- Como o banco Supabase e compartilhado, rollback de aplicacao nao deve depender de rollback automatico de schema. Migrations devem ser tratadas como etapa separada.
