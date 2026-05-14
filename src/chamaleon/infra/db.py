from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chamaleon.config import Settings
from chamaleon.infra.models import Base


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_engine(settings.database_url, future=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        if settings.auto_create_schema:
            Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Session:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
