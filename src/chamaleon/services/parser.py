from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from chamaleon.domain.types import IntentResult, TransactionDraft


CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "ifood": ("Alimentacao", "expense"),
    "rappi": ("Alimentacao", "expense"),
    "mercado": ("Compras", "expense"),
    "supermercado": ("Compras", "expense"),
    "uber": ("Transporte", "expense"),
    "99": ("Transporte", "expense"),
    "gasolina": ("Transporte", "expense"),
    "aluguel": ("Moradia", "expense"),
    "internet": ("Moradia", "expense"),
    "netflix": ("Entretenimento", "expense"),
    "spotify": ("Entretenimento", "expense"),
    "farmacia": ("Saude", "expense"),
    "dentista": ("Saude", "expense"),
    "curso": ("Educacao", "expense"),
    "livro": ("Educacao", "expense"),
    "freelance": ("Trabalho", "income"),
    "salario": ("Trabalho", "income"),
    "bonus": ("Trabalho", "income"),
    "pix": ("Trabalho", "income"),
    "cliente": ("Trabalho", "income"),
    "venda": ("Trabalho", "income"),
    "recebi": ("Trabalho", "income"),
}

INCOME_VERBS = {"recebi", "ganhei", "entrou", "caiu", "vendi", "faturei"}
EXPENSE_VERBS = {"gastei", "paguei", "comprei", "gasto", "debitei", "usei"}
SUMMARY_PATTERNS = ("quanto sobrou", "quanto tenho", "meu saldo", "saldo do mes", "resumo do mes")
HISTORY_PATTERNS = ("meu historico", "ultimas transacoes", "minhas transacoes", "historico")
REPORT_PATTERNS = ("me manda meu relatorio", "envia meu relatorio", "quero meu relatorio", "relatorio")
SALARY_PATTERNS = ("meu salario", "atualizar salario", "salario", "dinheiro")


def normalize_keyword(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9\s,./|:-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_amount(raw: str) -> Decimal | None:
    text = raw.strip().replace("R$", "").replace("r$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def detect_category(text: str) -> tuple[str, str]:
    normalized = normalize_keyword(text)
    compact = normalized.replace(" ", "")
    for keyword, category in CATEGORY_MAP.items():
        candidate = normalize_keyword(keyword)
        if candidate in normalized or candidate.replace(" ", "") in compact:
            return category
    return ("Outros", "expense")


def _extract_amount(text: str) -> tuple[Decimal | None, str]:
    match = re.search(r"(\d[\d\.,]*)", text)
    if not match:
        return None, text
    amount = normalize_amount(match.group(1))
    if amount is None:
        return None, text
    remaining = (text[: match.start()] + " " + text[match.end() :]).strip()
    return amount, re.sub(r"\s+", " ", remaining)


def _extract_details(text: str) -> tuple[str, str]:
    if "|" not in text:
        return text.strip(), ""
    main, details = text.split("|", 1)
    return main.strip(), details.strip()


def _extract_relative_date(text: str) -> tuple[date, str]:
    normalized = normalize_keyword(text)
    tx_date = date.today()
    if "ontem" in normalized:
        tx_date = date.today() - timedelta(days=1)
        normalized = normalized.replace("ontem", "").strip()
    elif "hoje" in normalized:
        normalized = normalized.replace("hoje", "").strip()
    return tx_date, normalized


def parse_transaction_text(text: str) -> TransactionDraft | None:
    cleaned = text.strip()
    if not cleaned:
        return None

    if cleaned.startswith("/registro"):
        cleaned = cleaned[len("/registro") :].strip()

    main_text, details = _extract_details(cleaned)
    tx_date, normalized = _extract_relative_date(main_text)
    amount, remaining = _extract_amount(normalized)
    if amount is None:
        return None

    category, tx_type = detect_category(remaining)
    lowered = normalize_keyword(remaining)
    if any(word in lowered.split() for word in INCOME_VERBS):
        tx_type = "income"
    elif any(word in lowered.split() for word in EXPENSE_VERBS):
        tx_type = "expense"

    description = remaining
    for filler in list(INCOME_VERBS | EXPENSE_VERBS) + ["de", "do", "da", "no", "na", "com"]:
        description = re.sub(rf"\b{re.escape(filler)}\b", " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip(" -") or "Transacao"

    confidence = 0.95 if category != "Outros" else 0.75
    if len(description.split()) == 1:
        confidence += 0.02
    return TransactionDraft(
        description=description[:80],
        amount=amount,
        category=category,
        transaction_type=tx_type,
        transaction_date=tx_date,
        details=details,
        confidence=min(confidence, 0.99),
        raw_text=text,
    )


def detect_intent(text: str) -> IntentResult:
    normalized = normalize_keyword(text)
    draft = parse_transaction_text(text)
    if draft:
        return IntentResult(
            intent="register_transaction",
            confidence=draft.confidence,
            entities={"category": draft.category, "type": draft.transaction_type},
            draft=draft,
        )
    if any(pattern in normalized for pattern in SUMMARY_PATTERNS):
        return IntentResult(intent="show_summary", confidence=0.92)
    if any(pattern in normalized for pattern in HISTORY_PATTERNS):
        return IntentResult(intent="show_history", confidence=0.90)
    if any(pattern in normalized for pattern in REPORT_PATTERNS):
        return IntentResult(intent="request_report", confidence=0.90)
    if any(pattern in normalized for pattern in SALARY_PATTERNS):
        amount, _ = _extract_amount(normalized)
        entities = {"amount": str(amount)} if amount is not None else {}
        return IntentResult(intent="update_salary", confidence=0.82, entities=entities)
    if normalized in {"ajuda", "menu", "comandos", "opcoes", "opções"}:
        return IntentResult(intent="help", confidence=0.99)
    return IntentResult(intent="unknown", confidence=0.0)


def draft_to_dict(draft: TransactionDraft) -> dict[str, str]:
    payload = asdict(draft)
    payload["amount"] = f"{draft.amount:.2f}"
    payload["transaction_date"] = draft.transaction_date.isoformat()
    return payload
