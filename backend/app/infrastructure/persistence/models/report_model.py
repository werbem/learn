"""SQLAlchemy ORM model for reports — skeleton."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ReportModel(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), nullable=False)
    our_company = Column(String(255), nullable=False)
    competitor_company = Column(String(255), nullable=False)
    product = Column(String(255), nullable=False)
    objective = Column(String(64), nullable=False)
    status = Column(String(32), default="pending")
    report_data = Column(Text, nullable=True)  # JSON string
    word_url = Column(String(512), nullable=True)
    total_duration_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
