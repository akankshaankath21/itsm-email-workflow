from typing import Optional, Literal, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, EmailStr, constr

class EnvelopeData(BaseModel):
    """Subset of envelope payload used by the mail classifier node."""
    subject: Optional[constr(max_length=500)] = Field(default=None)
    body: constr(min_length=1, max_length=20000)

class EnvelopeIn(BaseModel):
    """Incoming Gmail trigger envelope; extra keys are ignored."""
    model_config = ConfigDict(extra="ignore")
    data: EnvelopeData

class ClassificationOut(BaseModel):
    """Classifier output."""
    priority: Literal["P1", "P2", "P3"]
    label: constr(min_length=1, max_length=128)
    summary: constr(min_length=1, max_length=2000)

class ExecuteResponse(BaseModel):
    """HTTP response wrapper for mail classifier."""
    data: ClassificationOut


class GmailNodeConfigIn(BaseModel):
    """Configuration for creating a Gmail node."""
    name: constr(min_length=1, max_length=255)
    email_address: EmailStr
    credentials_file_path: constr(min_length=1, max_length=500)
    token_file_path: Optional[constr(max_length=500)] = "gmail_token.json"
    
    # Filtering options
    filter_sender: Optional[EmailStr] = None
    filter_subject_contains: Optional[constr(max_length=255)] = None
    only_unread: bool = True
    mark_as_read: bool = False
    
    # Polling configuration
    polling_interval: int = Field(ge=5, le=3600, default=30)  # 5 seconds to 1 hour
    max_results: int = Field(ge=1, le=100, default=10)

class GmailNodeOut(BaseModel):
    """Gmail node information for API responses."""
    id: UUID
    name: str
    email_address: str
    is_active: bool
    
    # Configuration
    filter_sender: Optional[str]
    filter_subject_contains: Optional[str]
    only_unread: bool
    mark_as_read: bool
    polling_interval: int
    max_results: int
    
    # Statistics
    emails_processed: int
    last_checked: Optional[datetime]
    last_email_received: Optional[datetime]
    
    # Metadata
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GmailNodeStatusOut(BaseModel):
    """Detailed Gmail node status."""
    id: UUID
    name: str
    email_address: str
    is_active: bool
    
    # Current state
    emails_processed: int
    last_checked: Optional[datetime]
    last_email_received: Optional[datetime]
    
    # Configuration summary
    polling_interval: int
    active_filters: List[str]  # Human-readable list of active filters
    
    # Recent activity (last 5 emails)
    recent_emails: List["RawEmailSummary"]

    model_config = ConfigDict(from_attributes=True)

class RawEmailOut(BaseModel):
    """Raw email data from Gmail."""
    id: UUID
    gmail_message_id: str
    gmail_thread_id: str
    
    from_address: str
    to_address: str
    cc_address: Optional[str]
    subject: Optional[str]
    body: str
    snippet: Optional[str]
    
    received_at: datetime
    is_read: bool
    labels: List[str]
    size_estimate: Optional[int]
    
    is_processed: bool
    processing_error: Optional[str]
    
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RawEmailSummary(BaseModel):
    """Summarized raw email for status responses."""
    id: UUID
    from_address: str
    subject: Optional[str]
    received_at: datetime
    is_processed: bool

    model_config = ConfigDict(from_attributes=True)

class EmailRecordOut(BaseModel):
    """Enhanced email classification record."""
    id: UUID
    subject: Optional[str]
    label: str
    priority: Literal["P1", "P2", "P3"]
    summary: str
    
    # Link back to original email
    raw_email_id: Optional[UUID]
    
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowExecutionIn(BaseModel):
    """Request to execute a workflow."""
    workflow_type: Literal["gmail_to_classifier", "manual_classify"]
    
    # For gmail_to_classifier workflow
    gmail_node_id: Optional[UUID] = None
    
    # For manual_classify workflow
    email_data: Optional[EnvelopeData] = None

class WorkflowExecutionOut(BaseModel):
    """Workflow execution result."""
    id: UUID
    workflow_type: str
    execution_status: Literal["running", "completed", "failed"]
    
    input_data: Optional[dict]
    output_data: Optional[dict]
    error_message: Optional[str]
    
    execution_time_ms: Optional[int]
    
    # Related entities
    gmail_node_id: Optional[UUID]
    raw_email_id: Optional[UUID]
    email_record_id: Optional[UUID]
    
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

class WorkflowStatusOut(BaseModel):
    """Comprehensive workflow status with related data."""
    execution: WorkflowExecutionOut
    
    # Related data (populated based on workflow type)
    gmail_node: Optional[GmailNodeOut] = None
    raw_email: Optional[RawEmailOut] = None
    classification: Optional[EmailRecordOut] = None


class GmailToClassifierResult(BaseModel):
    """Result of Gmail-to-Classifier workflow."""
    gmail_node: GmailNodeOut
    new_emails_found: int
    emails_classified: int
    classifications: List[ClassificationOut]
    execution_time_ms: int
    
class EmailHistoryOut(BaseModel):
    """Email history with classifications for a Gmail node."""
    gmail_node: GmailNodeOut
    total_emails: int
    emails: List["EmailWithClassifications"]

class EmailWithClassifications(BaseModel):
    """Raw email with its classification results."""
    raw_email: RawEmailOut
    classifications: List[EmailRecordOut]


class SuccessResponse(BaseModel):
    """Generic success response wrapper."""
    success: bool = True
    message: str
    data: Optional[dict] = None

class ErrorResponse(BaseModel):
    """Generic error response wrapper."""
    success: bool = False
    error: str
    details: Optional[str] = None

class ListResponse(BaseModel):
    """Generic list response wrapper."""
    items: List[dict]
    total: int
    page: int = 1
    page_size: int = 10

class GmailNodeActionRequest(BaseModel):
    """Request for Gmail node actions (start/stop)."""
    action: Literal["start", "stop", "restart"]

class BulkEmailClassifyRequest(BaseModel):
    """Request to classify multiple emails at once."""
    raw_email_ids: List[UUID] = Field(min_items=1, max_items=50)

# Update forward references
GmailNodeStatusOut.model_rebuild()
EmailHistoryOut.model_rebuild()
EmailWithClassifications.model_rebuild()