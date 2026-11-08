import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

JOB_KINDS = ("recognize_capture", "upload_image")
JOB_STATUSES = ("queued", "running", "succeeded", "failed")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('recognize_capture', 'upload_image')", name="ck_jobs_kind"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_jobs_status"),
        Index("ix_jobs_status_run_after", "status", "run_after"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    capture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("captures.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
