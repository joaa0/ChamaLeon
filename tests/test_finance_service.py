from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
except ModuleNotFoundError:  # pragma: no cover - depende do ambiente
    create_engine = None
    sessionmaker = None

if create_engine is not None:
    from chamaleon.infra.models import Base, User
    from chamaleon.repos.transactions import TransactionRepository
    from chamaleon.services.finance import FinanceService
    from chamaleon.services.parser import parse_transaction_text


@unittest.skipIf(create_engine is None, "sqlalchemy nao instalado no ambiente atual")
class FinanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.repo = TransactionRepository()
        self.service = FinanceService(self.repo)

    def test_builds_monthly_summary(self) -> None:
        with self.session_factory() as session:
            user = User(telegram_user_id="123", email="test@example.com", monthly_salary=Decimal("3000.00"))
            session.add(user)
            session.flush()

            expense = parse_transaction_text("gastei 100 no ifood")
            income = parse_transaction_text("recebi 250 de freelance")
            assert expense is not None and income is not None
            self.repo.create(session, user, expense)
            self.repo.create(session, user, income)
            session.commit()

            summary = self.service.build_monthly_summary(session, user, reference_date=date.today())

        self.assertEqual(summary.salary, Decimal("3000.00"))
        self.assertEqual(summary.expense_total, Decimal("100.00"))
        self.assertEqual(summary.income_total, Decimal("250.00"))
        self.assertEqual(summary.balance, Decimal("3150.00"))


if __name__ == "__main__":
    unittest.main()
