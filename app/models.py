import uuid
from datetime import datetime, timezone
from typing import Optional, Literal
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Enum, Text, DateTime, Index, Boolean, Integer, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db import Base

class EmailRecord(Base):
    """Persisted record for a classified email."""
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    label: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[Literal["P1", "P2", "P3"]] = mapped_column(Enum("P1", "P2", "P3", name="priority_enum"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Link to the raw email that was processed
    raw_email_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("raw_emails.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship to raw email
    raw_email: Mapped[Optional["RawEmail"]] = relationship("RawEmail", back_populates="classifications")

    __table_args__ = (
        Index("ix_emails_created_at", "created_at"),
        Index("ix_emails_priority", "priority"),
    )

class GmailNode(Base):
    """Gmail trigger node configuration and state."""
    __tablename__ = "gmail_nodes"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Gmail configuration
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    credentials_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    token_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Filtering configuration
    filter_sender: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filter_subject_contains: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    only_unread: Mapped[bool] = mapped_column(Boolean, default=True)
    mark_as_read: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Polling configuration
    polling_interval: Mapped[int] = mapped_column(Integer, default=30)
    max_results: Mapped[int] = mapped_column(Integer, default=10)
    
    # Node state
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_email_received: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    emails_processed: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    raw_emails: Mapped[list["RawEmail"]] = relationship("RawEmail", back_populates="gmail_node")

    __table_args__ = (
        Index("ix_gmail_nodes_email_address", "email_address"),
        Index("ix_gmail_nodes_is_active", "is_active"),
        Index("ix_gmail_nodes_created_at", "created_at"),
    )

class RawEmail(Base):
    """Raw email data from Gmail before classification."""
    __tablename__ = "raw_emails"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Gmail-specific fields
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Email content
    from_address: Mapped[str] = mapped_column(String(500), nullable=False)
    to_address: Mapped[str] = mapped_column(String(500), nullable=False)
    cc_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bcc_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Gmail metadata
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    size_estimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Processing state
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Foreign keys
    gmail_node_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gmail_nodes.id"), nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    gmail_node: Mapped["GmailNode"] = relationship("GmailNode", back_populates="raw_emails")
    classifications: Mapped[list["EmailRecord"]] = relationship("EmailRecord", back_populates="raw_email")

    __table_args__ = (
        Index("ix_raw_emails_gmail_message_id", "gmail_message_id"),
        Index("ix_raw_emails_gmail_node_id", "gmail_node_id"),
        Index("ix_raw_emails_received_at", "received_at"),
        Index("ix_raw_emails_is_processed", "is_processed"),
        Index("ix_raw_emails_created_at", "created_at"),
    )

class WorkflowExecution(Base):
    """Track workflow executions and their results."""
    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Workflow information
    workflow_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "gmail_to_classifier"
    execution_status: Mapped[Literal["running", "completed", "failed"]] = mapped_column(
        Enum("running", "completed", "failed", name="execution_status_enum"), nullable=False
    )
    
    # Input/Output data
    input_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Performance metrics
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Related entities
    gmail_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gmail_nodes.id"), nullable=True)
    raw_email_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("raw_emails.id"), nullable=True)
    email_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("emails.id"), nullable=True)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_workflow_executions_workflow_type", "workflow_type"),
        Index("ix_workflow_executions_execution_status", "execution_status"),
        Index("ix_workflow_executions_started_at", "started_at"),
        Index("ix_workflow_executions_gmail_node_id", "gmail_node_id"),
    )