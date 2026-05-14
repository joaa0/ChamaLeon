from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from chamaleon.infra.models import GeneratedReport, User


class ReportRepository:
    def upsert(self, session: Session, user: User, period_label: str, content: str, status: str = "generated") -> GeneratedReport:
        stmt = select(GeneratedReport).where(
            GeneratedReport.user_id == user.id,
            GeneratedReport.period_label == period_label,
        )
        report = session.scalar(stmt)
        if report is None:
            report = GeneratedReport(
                user_id=user.id,
                period_label=period_label,
                content=content,
                status=status,
            )
            session.add(report)
            session.flush()
            return report
        report.content = content
        report.status = status
        session.flush()
        return report
