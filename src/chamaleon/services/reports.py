from __future__ import annotations

from sqlalchemy.orm import Session

from chamaleon.config import Settings
from chamaleon.infra.ai import ReportAIClient
from chamaleon.infra.email import EmailClient
from chamaleon.infra.models import User
from chamaleon.repos.reports import ReportRepository
from chamaleon.services.finance import FinanceService


class ReportService:
    def __init__(
        self,
        settings: Settings,
        finance_service: FinanceService,
        report_repository: ReportRepository,
        ai_client: ReportAIClient,
        email_client: EmailClient,
    ):
        self.settings = settings
        self.finance_service = finance_service
        self.report_repository = report_repository
        self.ai_client = ai_client
        self.email_client = email_client

    def generate_and_send(self, session: Session, user: User) -> str:
        payload = self.finance_service.build_report_payload(session, user)
        content = self.ai_client.generate_report(payload)
        self.report_repository.upsert(session, user, payload.period_label, content, status="generated")
        self.email_client.send_report(user.email, self.settings.report_email_subject, content)
        self.report_repository.upsert(session, user, payload.period_label, content, status="sent")
        return content
