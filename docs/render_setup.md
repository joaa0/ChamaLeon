# Deploy no Render

## Arquitetura recomendada

- 1 banco PostgreSQL no Render
- 1 serviço Python para o bot
- variáveis de ambiente configuradas no dashboard

Como o bot usa polling do Telegram, o serviço deve rodar em instância única.

## Build e Start

### Build Command

```bash
pip install -r requirements.txt
```

### Start Command

```bash
alembic upgrade head && python3 ChamaLeon_telegram.py
```

## Variáveis de ambiente

Cole no serviço do bot:

```bash
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=<External Database URL do Render convertida para SQLAlchemy/psycopg>

APP_ENV=production
LOG_LEVEL=INFO
AUTO_CREATE_SCHEMA=false
CACHE_TTL_SECONDS=60

MISTRAL_API_KEY=...
OPENAI_MODEL=mistral-small-latest
OPENAI_BASE_URL=https://api.mistral.ai/v1

SMTP_HOST=...
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_USE_TLS=true
EMAIL_FROM=...
REPORT_EMAIL_SUBJECT=Seu relatorio financeiro ChamaLeon
```

## DATABASE_URL no formato certo

O código espera URL de SQLAlchemy com driver `psycopg`, por exemplo:

```bash
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

Se o Render te entregar uma URL começando com:

```bash
postgres://
```

troque para:

```bash
postgresql+psycopg://
```

Se ele te entregar:

```bash
postgresql://
```

troque para:

```bash
postgresql+psycopg://
```

## Checklist de subida

1. Criar o PostgreSQL no Render.
2. Criar o serviço Python que roda o bot.
3. Configurar todas as variáveis acima.
4. Confirmar que `DATABASE_URL` usa `postgresql+psycopg://`.
5. Fazer deploy.
6. Verificar no log se o Alembic rodou e se o polling do Telegram iniciou.

## Observações

- Se o SMTP ainda não estiver pronto, o bot continua funcionando, mas a geração de relatório não conseguirá entregar por e-mail.
- Se a chave do Mistral não estiver configurada, o bot cai no relatório determinístico de fallback.
- Para produção, não rode mais de uma instância do bot ao mesmo tempo.
