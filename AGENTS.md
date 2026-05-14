## Objetivo do projeto

Este é um sistema interno da Próspera Produções para gerenciar Ordens de Produção, chamadas de OPs.

O fluxo principal é:

1. Atendente cria uma OP com a data de finalização e se é ou não uma OP de prioridade alta.
2. Atendente seleciona os setores que estarão envolvidos.
3. PCP é notificado, então ele entra na nova OP e cria tarefas para cada setor, definindo os prazos individuais de cada tarefa.
4. Cada setor é notificado, então entra na OP e visualiza suas tarefas e marca como entregue.
5. Atendente recebe a notificação de entrega, podendo validar como entregue ou recusar.
6. Quando todas as tarefas forem entregues e validadas, a OP pode ser concluída ao atendente clicar em "OP finalizada".

## Stack atual

- Python
- Flask
- Jinja2
- SQLite
- SQLAlchemy
- Bootstrap
- CSS próprio em `static/css/theme.css`

## Regras importantes

- Não alterar código sem antes explicar o plano.
- Não quebrar o fluxo atual de OPs.
- Preservar o funcionamento de login, dashboard, calendário e notificações.
- Priorizar mudanças pequenas, seguras e testáveis.
- Sempre verificar se as rotas existem antes de criar botões ou links.
- Padronizar todos os templates usando `static/css/theme.css`.
- Manter o sistema simples, didático e fácil de entender.

## Problemas conhecidos

- `app.py` está concentrando responsabilidades demais.
- Algumas rotas usadas no HTML ainda não existem.
- Algumas páginas usam CSS inconsistente.
- Permissões precisam ser melhor centralizadas.
- O fluxo de usuários ativos/senha ainda precisa ser melhorado.
- OPSetor e Tarefa precisam ficar mais consistentes.
- Campo de alta prioridade ainda precisa ser implementado no model.

## Próximas prioridades

1. Corrigir rotas quebradas.
2. Criar modelos individuais para cada página mas manter e padronizar CSS.
3. Melhorar permissões com decorators.
4. Deixar o sistema de login com mais segurança e criar uma forma eficiente de cadastrar emails e permissões sem depender de entrar no backend.
5. Corrigir modelagem de OP, setor e tarefa.
6. Implementar alta prioridade.
7. Melhorar dashboard.
8. Só depois refatorar o `app.py` em Blueprints.

## Critério de conclusão

Antes de finalizar qualquer alteração:

- O projeto deve rodar sem erro.
- As páginas principais devem abrir.
- Nenhuma rota existente deve quebrar.
- O visual claro/escuro deve continuar funcionando.
- O fluxo de OP deve continuar coerente.
