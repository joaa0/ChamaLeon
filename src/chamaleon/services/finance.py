from __future__ import annotations

from calendar import monthrange
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from chamaleon.domain.types import MonthlySummary, ReportPayload
from chamaleon.infra.models import User
from chamaleon.repos.transactions import TransactionRepository


class FinanceService:
    def __init__(self, transactions: TransactionRepository):
        self.transactions = transactions

    def build_monthly_summary(self, session: Session, user: User, reference_date: date | None = None) -> MonthlySummary:
        today = reference_date or date.today()
        start_date = today.replace(day=1)
        end_date = today.replace(day=monthrange(today.year, today.month)[1])
        income_total, expense_total = self.transactions.monthly_totals(session, user, start_date, end_date)
        balance = Decimal(user.monthly_salary) + income_total - expense_total
        top_categories = self.transactions.monthly_category_totals(session, user, start_date, end_date)
        return MonthlySummary(
            salary=Decimal(user.monthly_salary),
            income_total=income_total,
            expense_total=expense_total,
            balance=balance,
            top_categories=top_categories[:5],
        )

    def build_report_payload(self, session: Session, user: User, reference_date: date | None = None) -> ReportPayload:
        today = reference_date or date.today()
        summary = self.build_monthly_summary(session, user, today)
        recent_transactions = []
        for transaction in self.transactions.list_recent(session, user, limit=8):
            recent_transactions.append(
                {
                    "id": transaction.id,
                    "date": transaction.transaction_date.isoformat(),
                    "type": transaction.transaction_type,
                    "category": transaction.category,
                    "description": transaction.description,
                    "details": transaction.details,
                    "amount": f"{transaction.amount:.2f}",
                }
            )
        return ReportPayload(
            period_label=today.strftime("%Y-%m"),
            generated_at=datetime.utcnow(),
            summary=summary,
            recent_transactions=recent_transactions,
            email=user.email,
        )
