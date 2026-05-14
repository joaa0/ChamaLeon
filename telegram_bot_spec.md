# ChamaLeon — Especificacao Tecnica

Documento tecnico alinhado ao runtime modular atual.

## Visao geral

O ChamaLeon e um bot financeiro conversacional para Telegram. O runtime atual foi reorganizado para operar com PostgreSQL e servicos Python locais, sem depender de Google Sheets ou Zapier.

Fonte principal do runtime:

- [src/chamaleon/bot/app.py](/home/jj/ChamaLeon-main/src/chamaleon/bot/app.py)

## Componentes

### Camada `bot`

Responsavel por:

- handlers Telegram;
- callbacks de menu;
- onboarding;
- confirmacao de transacoes;
- roteamento entre estados guiados e intents conversacionais.

### Camada `services`

Responsavel por:

- parser heuristico de linguagem natural;
- montagem de sumario mensal;
- geracao e envio de relatorio.

### Camada `repos`

Responsavel por:

- `UserRepository`
- `TransactionRepository`
- `ReportRepository`

### Camada `infra`

Responsavel por:

- configuracao por ambiente;
- engine SQLAlchemy;
- modelos do banco;
- cliente de IA;
- cliente SMTP;
- logging.

## Comandos registrados

- `/start`
- `/registro`
- `/historico`
- `/salario`
- `/dinheiro`
- `/relatorio`

Observacao:

- `/salario` e `/dinheiro` convergem para o mesmo resumo financeiro.

## Intents conversacionais

O parser atual tenta identificar:

- `register_transaction`
- `show_history`
- `show_summary`
- `update_salary`
- `request_report`
- `help`

Exemplos suportados:

```text
gastei 39 no ifood
recebi 1200 de freelance
ontem paguei 82 no mercado
quanto sobrou esse mes?
me manda meu relatorio
```

## Contratos internos principais

### `TransactionDraft`

- `description`
- `amount`
- `category`
- `transaction_type`
- `transaction_date`
- `details`
- `confidence`
- `raw_text`

### `IntentResult`

- `intent`
- `confidence`
- `entities`
- `draft`

### `MonthlySummary`

- `salary`
- `income_total`
- `expense_total`
- `balance`
- `top_categories`

## Persistencia

### `users`

- `telegram_user_id`
- `email`
- `monthly_salary`
- timestamps

### `transactions`

- `user_id`
- `transaction_type`
- `category`
- `description`
- `details`
- `amount`
- `transaction_date`
- timestamps

### `generated_reports`

- `user_id`
- `period_label`
- `status`
- `delivery_channel`
- `content`
- timestamps

## Fluxos implementados

### Onboarding

```text
/start
-> se user inexistente:
   -> awaiting_email
   -> awaiting_onboarding_salary
   -> create_or_update em users
-> senao:
   -> menu principal
```

### Registro de transacao

```text
mensagem ou /registro
-> parse_transaction_text()
-> pending_transaction
-> confirmacao via botao ou texto
-> create() em transactions
```

### Historico

```text
/historico ou intent "historico"
-> count_for_user()
-> list_recent()
-> pagina com callbacks history:{page}
```

### Resumo financeiro

```text
/salario, /dinheiro ou intent equivalente
-> build_monthly_summary()
-> salario + entradas - gastos
```

### Relatorio

```text
/relatorio ou intent equivalente
-> build_report_payload()
-> ReportAIClient.generate_report()
-> ReportRepository.upsert()
-> EmailClient.send_report()
```

## Variaveis de ambiente

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `APP_ENV`
- `LOG_LEVEL`
- `AUTO_CREATE_SCHEMA`
- `MISTRAL_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `EMAIL_FROM`
- `REPORT_EMAIL_SUBJECT`

## Validacao esperada

- `python3 -m py_compile` nos arquivos Python principais;
- `python3 -m unittest tests.test_parser tests.test_finance_service`;
- `alembic upgrade head` com `DATABASE_URL` valido.

## Lacunas e problemas atuais

- o parser e robusto para casos frequentes, mas continua baseado em heuristica e palavras-chave;
- a camada de estado ainda depende de memoria de processo do Telegram bot;
- o cliente de IA usa API OpenAI-compatible via HTTP bruto e pressupoe contrato padrao de `chat/completions`;
- ainda nao existe fila assíncrona para geracao de relatorios, entao a solicitacao roda no fluxo do bot;
- a seguranca operacional agora depende da postura do banco, do SMTP e da chave do provedor de IA, e isso precisa ser endurecido antes de uma carga maior.
