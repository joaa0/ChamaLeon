# Arquitetura do Produto ChamaLeon

## Objetivo

O runtime do ChamaLeon deixou de depender de Google Sheets e Zapier. A aplicacao agora usa PostgreSQL como fonte de verdade e organiza o bot em camadas Python menores e testaveis.

## Estrutura de Pastas

```text
src/chamaleon/
  bot/        -> handlers Telegram, callbacks e entrypoint da aplicacao
  domain/     -> tipos internos e contratos
  infra/      -> banco, modelos SQLAlchemy, logging, email e IA
  repos/      -> acesso a users, transactions e generated_reports
  services/   -> parser conversacional, resumo financeiro e relatorios
alembic/      -> migracoes do banco
tests/        -> parser e servicos principais
```

## Fluxo de Dados

1. O usuario envia texto natural ou comando no Telegram.
2. `bot/app.py` identifica onboarding, fluxo guiado ou intent conversacional.
3. `services/parser.py` extrai intent e rascunho de transacao.
4. `repos/` persiste e consulta dados no PostgreSQL.
5. `services/finance.py` calcula o resumo mensal.
6. `services/reports.py` monta o contexto, usa `infra/ai.py` e envia o email por `infra/email.py`.

## Banco de Dados

Tabelas iniciais:

- `users`
- `transactions`
- `generated_reports`

As migracoes ficam versionadas em `alembic/versions/`.

## Compatibilidade

- `ChamaLeon_telegram.py` permanece como entrypoint do deploy.
- `/registro`, `/historico`, `/salario`, `/dinheiro` e `/relatorio` continuam funcionando.
- Mensagens naturais como `gastei 39 no ifood` e `quanto sobrou esse mes?` passam a ser tratadas como fluxo principal.
