## Visao geral do projeto

Este e um sistema interno da Prospera Producoes para gestao de Ordens de Producao, chamadas de OPs.

O fluxo principal e:

1. Atendente cria uma OP, define prazo final e marca alta prioridade quando necessario.
2. Atendente seleciona os setores envolvidos.
3. PCP e notificado, acessa a OP e cria tarefas para cada setor com prazos individuais.
4. Cada setor e notificado, acessa suas tarefas e marca entregas.
5. Atendente ou usuario autorizado valida ou recusa entregas.
6. Quando todas as tarefas forem entregues e validadas, a OP pode ser finalizada.

## Stack principal

- Python
- Flask
- Jinja2
- SQLAlchemy
- Flask-Migrate/Alembic
- PostgreSQL/Supabase em producao
- SQLite apenas para desenvolvimento/testes, quando aplicavel
- Render para deploy
- Bootstrap
- CSS proprio em `static/css/theme.css`

## Principais areas do sistema

- Autenticacao, login, cadastro com codigo por e-mail e recuperacao de senha.
- Usuarios, permissoes e status ativo/inativo.
- OPs, setores envolvidos e tarefas por setor.
- Dashboard, kanban, calendario e metricas.
- Notificacoes internas e e-mails operacionais.
- Slides TV.
- Arquivamento de OPs.

## Papeis de usuario

- `ADMIN`: administra usuarios, permissoes e acessa as areas de gestao.
- `ATENDENTE`: cria e acompanha OPs, valida entregas e finaliza OPs.
- `PCP`: planeja OPs e cria tarefas para setores.
- `SETOR`: executa tarefas do setor vinculado.
- `ESPECTADOR`: visualiza informacoes permitidas sem executar acoes operacionais.

## Regras importantes

- Nao alterar codigo sem antes explicar o plano.
- Nao fazer commit automaticamente.
- Nao expor credenciais, tokens, senhas ou codigos sensiveis em codigo, logs ou mensagens de erro.
- Nao usar dados de teste em producao.
- `APP_ENV=production` deve exigir banco PostgreSQL valido.
- Seeds, usuarios de teste e rotas de teste devem ficar restritos a `development`, `test` ou ambientes locais.
- Preservar login, dashboard, calendario, kanban, notificacoes e fluxo de OPs.
- Preservar regras de permissao existentes ao alterar rotas ou templates.
- Sempre verificar se uma rota existe antes de criar botoes ou links.
- Preferir arquivar OPs em vez de excluir dados operacionais.
- Padronizar templates usando `static/css/theme.css`.
- Manter mudancas pequenas, seguras, didaticas e testaveis.
- Manter testes passando antes de finalizar qualquer alteracao.
- Refatorar `app.py` em Blueprints somente depois de estabilizar rotas, permissoes, modelos e fluxos principais.

## E-mails

O sistema depende de e-mail para fluxos criticos:

- Codigo de cadastro/validacao de usuario.
- Codigo de recuperacao de senha.
- Notificacoes operacionais futuras ou ja existentes.

Toda logica de envio deve passar por `email_service.py`. Rotas nao devem montar SMTP diretamente nem conter credenciais.

Variaveis de ambiente esperadas:

```env
MAIL_ENABLED=false
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=usuario@example.com
MAIL_PASSWORD=senha-ou-token-do-provedor
MAIL_DEFAULT_SENDER=sistema@example.com
EMAILS_OPERACIONAIS_ATIVOS=false
```

Regras de seguranca para e-mail:

- Em producao, habilitar envio real somente com `MAIL_ENABLED=true` e SMTP completo.
- E-mails operacionais consolidados tambem exigem `EMAILS_OPERACIONAIS_ATIVOS=true`.
- Em desenvolvimento/testes, manter envio real desativado quando nao for necessario.
- Testes nunca devem enviar e-mails reais.
- Nunca logar senha, token SMTP ou codigo completo de verificacao.
- Erros SMTP devem gerar mensagem amigavel para o usuario.

## Relatorio operacional consolidado

O comando do relatorio operacional e:

```powershell
$env:FLASK_APP = "app.py"
flask enviar-relatorio-operacional --janela 10h
flask enviar-relatorio-operacional --janela 15h
```

Regras obrigatorias:

- O relatorio e sempre individual por usuario.
- Nao enviar email coletivo para setor.
- Nao colocar varios usuarios no mesmo `to` nem expor emails de outros usuarios.
- Tarefa com responsavel especifico entra apenas no relatorio dos responsaveis atribuidos.
- Tarefa sem responsavel especifico entra no relatorio individual de todos os usuarios ativos do setor vinculado.
- `SETOR` nunca recebe tarefa de outro setor.
- `PCP` recebe visao operacional ampla, sempre individual.
- `ATENDENTE` recebe itens das OPs relacionadas a ele por `OP.atendente`.
- `ADMIN` nao deve ser incluido automaticamente em tudo sem regra explicita.
- `ESPECTADOR` nao recebe relatorio operacional.
- Se nao houver pendencia relevante, nao enviar email vazio.

Horarios:

- 10h em `America/Sao_Paulo`, normalmente 13h UTC no Render.
- 15h em `America/Sao_Paulo`, normalmente 18h UTC no Render.

Controle:

- A tabela `notification_email_deliveries` registra entregas e pulos por usuario, janela e data operacional.
- O objetivo e impedir duplicidade de envio para o mesmo usuario na mesma janela/data.
- `MAIL_ENABLED=false`, `EMAILS_OPERACIONAIS_ATIVOS=false` ou SMTP incompleto devem impedir envio real e registrar motivo seguro.

## Variaveis principais de ambiente

```env
APP_ENV=development
SECRET_KEY=troque-por-um-valor-forte
DATABASE_URL=postgresql://usuario:senha@host:5432/banco
APP_BASE_URL=https://seu-servico.onrender.com
MAIL_ENABLED=false
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=usuario@example.com
MAIL_PASSWORD=senha-ou-token-do-provedor
MAIL_DEFAULT_SENDER=sistema@example.com
EMAILS_OPERACIONAIS_ATIVOS=false
```

Nao preencher valores reais em arquivos versionados.

## Comandos uteis

Rodar testes:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Iniciar app localmente:

```powershell
$env:FLASK_APP = "app.py"
$env:APP_ENV = "development"
flask run
```

Rodar migracoes pendentes:

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
```

Criar nova migracao:

```powershell
$env:FLASK_APP = "app.py"
flask db migrate -m "descricao_da_migracao"
```

Aplicar migracao:

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
```

Criar primeiro administrador:

```powershell
$env:FLASK_APP = "app.py"
flask criar-admin
```

Testar SMTP real manualmente:

```powershell
$env:FLASK_APP = "app.py"
flask testar-email --para email@dominio.com
```

## Criterio de conclusao

Antes de finalizar qualquer alteracao:

- O projeto deve rodar sem erro.
- As paginas principais devem abrir.
- Nenhuma rota existente deve quebrar.
- O visual claro/escuro deve continuar funcionando.
- O fluxo de OP deve continuar coerente.
- Testes relevantes devem passar.
