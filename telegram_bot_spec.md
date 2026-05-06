# ChamaLeon — Especificação Técnica

## 1. Visão geral

O **ChamaLeon** é um assistente financeiro conversacional integrado ao Telegram.

Ele permite que o usuário:

- faça onboarding com e-mail e salário;
- registre gastos e recebimentos por mensagem;
- adicione observações opcionais com `|`;
- consulte histórico paginado;
- visualize resumo mensal;
- atualize salário;
- delete transações;
- solicite relatório financeiro personalizado por e-mail com apoio da Mistral AI.

A arquitetura atual combina:

```text
Telegram → Bot Python → Google Sheets + Zapier → Mistral AI → E-mail
```

O arquivo principal de execução do bot é:

```bash
ChamaLeon_telegram.py
```

---

## 2. Stack utilizada

| Camada | Tecnologia | Função |
|---|---|---|
| Interface | Telegram Bot | Entrada e saída conversacional |
| Lógica | Python | Estados, validação, parse, cache, payloads |
| Persistência | Google Sheets | Abas `users` e `transactions` |
| Integração | Zapier | Automação dos fluxos externos |
| IA | Mistral AI | Geração textual do relatório financeiro |
| E-mail | Email by Zapier | Envio do relatório final |

---

## 3. Comandos implementados

| Comando | Função |
|---|---|
| `/start` | Inicia o bot e verifica onboarding |
| `/registro` | Registra gasto ou recebimento |
| `/historico` | Mostra histórico paginado |
| `/salario` | Mostra resumo financeiro e permite atualizar salário |
| `/dinheiro` | Alias funcional de `/salario` |
| `/relatorio` | Solicita relatório financeiro por e-mail |

Observação:

- `/dinheiro` **não é uma lacuna**. Ele está implementado como alias de `/salario`.
- Ambos usam a mesma lógica de resumo mensal.

---

## 4. Estrutura do Google Sheets

### 4.1 Aba `users`

| Coluna | Campo | Descrição |
|---|---|---|
| A | `user_id` | ID do usuário no Telegram |
| B | `email` | E-mail para envio do relatório |
| C | `registered_date` | Data de cadastro |
| D | `salary` | Salário base |
| E | `updated_at` | Última atualização |

### 4.2 Aba `transactions`

| Coluna | Campo | Descrição |
|---|---|---|
| A | `id` | ID único da transação |
| B | `user_id` | ID do usuário no Telegram |
| C | `date` | Data da transação |
| D | `description` | Descrição curta |
| E | `category` | Categoria |
| F | `amount` | Valor |
| G | `type` | `expense` ou `income` |
| H | `created_at` | Data de criação |
| I | `updated_at` | Última atualização |
| J | `details` | Observações opcionais |

---

## 5. Fluxos principais do bot

## 5.1 Onboarding

Fluxo:

```text
/start
→ verificar user_id na aba users
→ se usuário não existir ou estiver sem salário válido: pedir e-mail
→ validar e-mail
→ pedir salário
→ salvar/atualizar usuário na aba users via gspread
→ liberar menu principal
```

O onboarding inicial é salvo diretamente pelo bot usando `gspread`.

Ele **não passa pelo Zap 2**.

O usuário só é considerado apto quando existe uma linha na aba `users` com salário válido.

---

## 5.2 Registro de transações

Exemplos aceitos:

```text
/registro ifood 39
/registro mercado 84 | compra do mês
/registro freelance 800 | projeto abril
```

O bot:

1. separa `description`, `amount` e `details`;
2. normaliza o valor;
3. detecta categoria e tipo;
4. mostra confirmação;
5. após confirmação, envia `action=create` para o Zap 1;
6. invalida o cache de `transactions` e `salary_summary`.

Payload enviado ao Zap 1:

```json
{
  "action": "create",
  "user_id": "7500965215",
  "description": "mercado",
  "details": "compra do mês",
  "amount": 84.0,
  "category": "Compras",
  "type": "expense",
  "date": "2026-05-06",
  "_source": "telegram_bot",
  "_timestamp": "2026-05-06T12:00:00",
  "_normalized": true
}
```

---

## 5.3 Histórico

O histórico principal **não depende do Zap 1**.

Fluxo atual:

```text
Bot → gspread → aba transactions → filtro por user_id → paginação → Telegram
```

O Zap 1 ainda possui branch `READ`, mas ela é considerada **legada**.

---

## 5.4 Resumo mensal

O resumo mensal é calculado diretamente pelo bot.

Fórmula:

```text
saldo disponível = salário registrado + entradas do mês - gastos do mês
```

O bot lê:

- salário na aba `users`;
- transações do mês atual na aba `transactions`;
- entradas (`income`);
- gastos (`expense`).

Formatos aceitos para datas e valores:

- `YYYY-MM-DD`
- `DD/MM/YYYY`
- ISO com hora
- serial date do Google Sheets
- `50`
- `50.00`
- `50,00`
- `R$ 50,00`

---

## 5.5 Atualização de salário

A atualização de salário é feita pelo Zap 2.

Fluxo:

```text
Usuário abre Meu Dinheiro / Meu Salário
→ clica em Registrar / Atualizar
→ informa o valor
→ Bot envia action=update_salary para o Zap 2
→ Zap 2 atualiza salary e updated_at na aba users
```

Payload:

```json
{
  "action": "update_salary",
  "user_id": "7500965215",
  "salary": 3500.0,
  "_source": "telegram_bot",
  "_timestamp": "2026-05-06T12:00:00"
}
```

---

## 5.6 Deleção de transações

Fluxo:

```text
Usuário escolhe Deletar Transação
→ Bot lista até 10 transações recentes do próprio usuário
→ Usuário seleciona uma
→ Bot mostra confirmação
→ Usuário confirma
→ Bot envia action=delete para o Zap 1
→ Zap 1 remove a linha correspondente no Google Sheets
```

Proteção lógica atual:

- o bot lista apenas transações filtradas pelo `user_id` do usuário atual;
- a transação deletada precisa ter vindo dessa lista;
- depois do sucesso, os caches `transactions` e `salary_summary` são invalidados.

Payload:

```json
{
  "action": "delete",
  "user_id": "7500965215",
  "transaction_id": "7500965215_20260506120000",
  "_source": "telegram_bot",
  "_timestamp": "2026-05-06T12:00:00"
}
```

---

## 5.7 Relatório por e-mail

O relatório é solicitado pelo bot e gerado pela branch `REPORT` do Zap 1.

Fluxo:

```text
Bot envia action=report
→ Zap 1 busca dados do usuário
→ Zap 1 busca transações do mês
→ Code Step prepara métricas financeiras
→ Mistral AI gera análise textual
→ Zapier formata HTML
→ E-mail é enviado ao usuário
```

Payload:

```json
{
  "action": "report",
  "user_id": "7500965215",
  "_source": "telegram_bot",
  "_timestamp": "2026-05-06T12:00:00"
}
```

O relatório é do **mês atual** e é enviado quando o usuário solicita.

---

## 6. Zap 1 — Fluxo principal

O Zap 1 processa ações relacionadas a transações e relatório.

Branches atuais:

| Branch | Status | Função |
|---|---|---|
| `CREATE` | Ativa | Salva nova transação na aba `transactions` |
| `READ` | Legada | Consulta transações pelo Zapier |
| `DELETE` | Ativa | Remove transação pelo ID |
| `REPORT` | Ativa | Gera relatório com IA e envia por e-mail |

Observação importante:

- O Zap 1 **não deve ser descrito como CRUD completo com Update**.
- O fluxo atual cobre `CREATE`, `READ` legado, `DELETE` e `REPORT`.
- Não há fluxo principal de `UPDATE` de transação.

---

## 7. Zap 2 — Atualização de salário

O Zap 2 é isolado para salário.

Ele deve processar apenas:

```text
user_id + salary
```

Fluxo:

```text
Webhook
→ Code by Zapier
→ Filter entity=user
→ Lookup na aba users
→ Update salary e updated_at
```

O Zap 2 **não deve conter**:

- transações;
- categorias;
- valores de gastos;
- IA;
- múltiplos paths;
- relatório;
- `description`;
- `amount`;
- `type`;
- `transaction_id`.

Motivo da separação:

```text
salary pertence à entidade user
transaction pertence à entidade transaction
```

Separar os fluxos reduz ambiguidade, duplicação de usuário e desalinhamento de colunas.

---

## 8. Relatório com IA e prompt

A branch `REPORT` monta um payload financeiro com:

- salário;
- entradas adicionais;
- total de despesas;
- saldo final;
- percentual da renda comprometida;
- totais por categoria;
- maiores transações;
- sinais financeiros;
- sinais comportamentais.

A Mistral AI gera resposta em 5 seções:

1. Planilha resumida de gastos.
2. Diagnóstico financeiro.
3. Ajuste principal.
4. Novo cenário após ajuste.
5. Uso da sobra.

Guardrails principais:

- tratar inferências como hipóteses;
- não prometer resultado financeiro;
- não recomendar produtos financeiros específicos;
- evitar linguagem absoluta;
- não sugerir cortes agressivos em saúde ou educação;
- se houver déficit, priorizar equilíbrio antes de reserva;
- sugerir faixas de ajuste, não valores rígidos.

---

## 9. Categorização

O bot usa keyword matching local para inferir categoria e tipo.

| Exemplo | Categoria | Tipo |
|---|---|---|
| `ifood 39` | Alimentação | `expense` |
| `uber 25` | Transporte | `expense` |
| `mercado 300` | Compras | `expense` |
| `curso 100` | Educação | `expense` |
| `freelance 800` | Trabalho | `income` |
| `salário 3500` | Trabalho | `income` |
| sem correspondência | Outros | `expense` |

Categorias principais do bot:

- Alimentação
- Transporte
- Entretenimento
- Saúde
- Educação
- Moradia
- Compras
- Outros

A branch `REPORT` pode aplicar normalizações adicionais para fins de análise financeira.

---

## 10. Cache local

O bot usa cache simples em memória dentro de `context.user_data["_cache"]`.

Configuração:

```text
TTL = 60 segundos
```

Chaves atuais:

| Chave | Uso |
|---|---|
| `transactions` | Histórico e deleção |
| `salary_summary` | Salário, entradas, gastos e saldo mensal |

Invalidações:

| Evento | Cache invalidado |
|---|---|
| Criação de transação | `transactions`, `salary_summary` |
| Deleção de transação | `transactions`, `salary_summary` |
| Atualização de salário | `salary_summary` |

---

## 11. Variáveis de ambiente

```bash
TELEGRAM_BOT_TOKEN=

ZAPIER_WEBHOOK_EXPENSE=
ZAPIER_WEBHOOK_SALARY=

GOOGLE_SHEET_ID=
GOOGLE_CREDENTIALS_PATH=
GOOGLE_CREDENTIALS_JSON=

SHEET_NAME=transactions
USERS_SHEET_NAME=users
```

É necessário usar uma das opções:

```text
GOOGLE_CREDENTIALS_PATH
ou
GOOGLE_CREDENTIALS_JSON
```

Em ambiente cloud, `GOOGLE_CREDENTIALS_JSON` deve preservar corretamente a `private_key`.

O código corrige `\n` para `
` antes de autenticar.

---

## 12. Dependências

`requirements.txt` atual:

```txt
python-telegram-bot==21.1
requests==2.31.0
python-dotenv==1.0.0
gspread==5.12.0
google-auth
```

---

## 13. Execução local

```bash
python3 ChamaLeon_telegram.py
```

O bot roda em polling.

Apenas uma instância deve rodar por vez.

---

## 14. Deploy

Procfile esperado:

```text
worker: python ChamaLeon_telegram.py
```

Checklist:

1. configurar variáveis de ambiente;
2. compartilhar a planilha com a service account;
3. publicar Zap 1;
4. publicar Zap 2;
5. garantir apenas uma instância de polling;
6. acompanhar logs de conexão com Google Sheets, Zap 1 e Zap 2.

---

## 15. Limitações conhecidas

| Limitação | Impacto |
|---|---|
| Google Sheets como banco | Adequado para protótipo, limitado para escala |
| Estado em memória | Restart pode interromper fluxos em andamento |
| Webhooks sem autenticação própria | Ponto sensível operacional |
| Relatório depende do Zap 1 | Geração final não vive totalmente no repositório Python |
| Logs verbosos | Úteis para debug, mas devem ser reduzidos em produção |
| Polling | Não deve rodar em múltiplas instâncias |
| READ do Zap 1 legado | Histórico principal já é via `gspread` |

---

## 16. Status consolidado

| Área | Status |
|---|---|
| Onboarding por e-mail e salário | Funcional |
| Registro de transações | Funcional |
| Campo `details` com `|` | Funcional |
| Histórico via `gspread` | Funcional |
| Resumo mensal | Funcional |
| `/salario` | Funcional |
| `/dinheiro` | Funcional como alias de `/salario` |
| Deleção via Zap 1 | Funcional |
| Atualização de salário via Zap 2 | Funcional |
| Relatório por e-mail | Funcional no sistema integrado |
| Cache local | Implementado |
| Estado persistente | Não implementado |
| Banco relacional | Não implementado |

---

## 17. Próximos passos naturais

- substituir Google Sheets por Supabase/PostgreSQL;
- adicionar autenticação/validação mais forte nos webhooks;
- persistir estado de conversa;
- reduzir logs de debug em produção;
- enriquecer relatório com comparação entre meses;
- adicionar gastos recorrentes.
