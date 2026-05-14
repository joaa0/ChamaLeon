from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from chamaleon.infra.models import User


class UserRepository:
    def get_by_telegram_id(self, session: Session, telegram_user_id: str) -> User | None:
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        return session.scalar(stmt)

    def create_or_update(self, session: Session, telegram_user_id: str, email: str, monthly_salary: Decimal) -> User:
        user = self.get_by_telegram_id(session, telegram_user_id)
        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                email=email,
                monthly_salary=monthly_salary,
            )
            session.add(user)
            session.flush()
            return user
        user.email = email
        user.monthly_salary = monthly_salary
        session.flush()
        return user

    def update_salary(self, session: Session, telegram_user_id: str, monthly_salary: Decimal) -> User | None:
        user = self.get_by_telegram_id(session, telegram_user_id)
        if user is None:
            return None
        user.monthly_salary = monthly_salary
        session.flush()
        return user
