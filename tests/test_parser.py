from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chamaleon.services.parser import detect_intent, parse_transaction_text


class ParserTests(unittest.TestCase):
    def test_parses_expense_sentence(self) -> None:
        draft = parse_transaction_text("gastei 39 no ifood")
        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertEqual(draft.transaction_type, "expense")
        self.assertEqual(draft.category, "Alimentacao")
        self.assertEqual(draft.amount, Decimal("39.00"))

    def test_parses_income_sentence(self) -> None:
        draft = parse_transaction_text("recebi 1200 de freelance")
        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertEqual(draft.transaction_type, "income")
        self.assertEqual(draft.category, "Trabalho")
        self.assertEqual(draft.amount, Decimal("1200.00"))

    def test_parses_yesterday_reference(self) -> None:
        draft = parse_transaction_text("ontem paguei 82 no mercado")
        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertEqual(draft.transaction_date, date.today() - timedelta(days=1))

    def test_detects_summary_intent(self) -> None:
        intent = detect_intent("quanto sobrou esse mes?")
        self.assertEqual(intent.intent, "show_summary")


if __name__ == "__main__":
    unittest.main()
