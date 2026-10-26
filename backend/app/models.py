"""Database tables."""
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import clock
from .db import Base


def utcnow() -> datetime:
    return clock.now()


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    aicte_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))  # Engineering, Pharmacy, Management, Polytechnic
    state: Mapped[str] = mapped_column(String(60))
    state_code: Mapped[str] = mapped_column(String(4))
    city: Mapped[str] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(String(300))
    region: Mapped[str] = mapped_column(String(40))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    established: Mapped[int] = mapped_column(Integer)
    university: Mapped[str] = mapped_column(String(200))


class InstitutionRecord(Base):
    """Records already held in authorised AICTE systems (previous approvals, intake, faculty, TER)."""
    __tablename__ = "institution_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    last_approved_cycle: Mapped[str] = mapped_column(String(10))
    approval_status: Mapped[str] = mapped_column(String(30))
    programmes: Mapped[list] = mapped_column(JSON, default=list)  # [{programme, level, approved_intake}]
    faculty: Mapped[list] = mapped_column(JSON, default=list)  # [{faculty_id, name, qualification, designation}]
    open_deficiencies: Mapped[int] = mapped_column(Integer, default=0)
    affidavit_on_file: Mapped[bool] = mapped_column(Boolean, default=True)
    accreditation_no: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))  # institution, scrutinizer, senior_officer, rule_admin, auditor
    institution_id: Mapped[Optional[str]] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    app_type: Mapped[str] = mapped_column(String(30))  # EOA, INTAKE_INCREASE, NEW_PROGRAMME
    cycle: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    form: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    overall_status: Mapped[str] = mapped_column(String(30), default="NOT_CHECKED")
    rulebook_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    precheck_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    institution: Mapped[Institution] = relationship()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    slot: Mapped[str] = mapped_column(String(40))  # checklist slot the institution uploaded into
    detected_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    detected_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(60))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(100))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[list] = mapped_column(JSON, default=list)  # [{w, h}] in points
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED")  # UPLOADED, PROCESSING, PROCESSED, FAILED
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # TEXT_LAYER, OCR, NONE
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    phash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    qr_payload: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    signature: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    fields: Mapped[list["ExtractedField"]] = relationship(cascade="all, delete-orphan", order_by="ExtractedField.id")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    value: Mapped[str] = mapped_column(String(400))
    normalized: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    bbox: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [x0, y0, x1, y1] in PDF points
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class PrecheckRun(Base):
    __tablename__ = "precheck_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(120))
    rulebook_version: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    document_id: Mapped[Optional[str]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(40))
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30))  # VERIFIED, MISMATCH, EXPIRED, PENDING, SOURCE_UNAVAILABLE, MANUAL_REVIEW
    compared: Mapped[list] = mapped_column(JSON, default=list)
    response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(30))  # MISSING_DOCUMENT, EXPIRED_DOCUMENT, INCONSISTENCY, ANOMALY, VERIFICATION, COMPLIANCE_GAP, QUALITY
    severity: Mapped[str] = mapped_column(String(10))  # critical, high, warning, info
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    rule_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    preliminary: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_to_institution: Mapped[bool] = mapped_column(Boolean, default=True)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN, ACCEPTED, OVERRIDDEN, SUPERSEDED, RESOLVED
    decision_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RulebookVersion(Base):
    __tablename__ = "rulebook_versions"
    __table_args__ = (UniqueConstraint("cycle", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # DRAFT, PENDING_APPROVAL, PUBLISHED, RETIRED, REJECTED
    content: Mapped[dict] = mapped_column(JSON)
    change_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    dry_run: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    @property
    def label(self) -> str:
        return f"APH {self.cycle} v{self.version}"


class Letter(Base):
    __tablename__ = "letters"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")  # DRAFT, PENDING_APPROVAL, ISSUED, RESPONDED, WITHDRAWN
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{finding_id, title, text}]
    note: Mapped[str] = mapped_column(Text, default="")
    drafted_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    severity: Mapped[str] = mapped_column(String(10))  # critical, serious, warning, info
    kind: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(400))
    application_id: Mapped[Optional[str]] = mapped_column(ForeignKey("applications.id"), nullable=True)
    audience: Mapped[str] = mapped_column(String(30))  # role name, or "institution:<id>"
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    read_by: Mapped[list] = mapped_column(JSON, default=list)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(120))
    actor_type: Mapped[str] = mapped_column(String(20))  # USER, SYSTEM, ADAPTER
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(80))
    application_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)  # QUEUED, RUNNING, DONE, FAILED
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
