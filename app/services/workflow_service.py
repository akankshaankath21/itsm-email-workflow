import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, insert
from sqlalchemy.orm import selectinload

from app.models import GmailNode, RawEmail, EmailRecord, WorkflowExecution
from app.schemas import EnvelopeIn, EnvelopeData, ClassificationOut
from app.services.gmail_service import GmailService
from app.services.classifier_service import ClassifierService

class WorkflowService:
    """Service for managing multi-node workflows with proper persistence."""
    
    def __init__(self):
        self.gmail_service = GmailService()
        self.classifier_service = ClassifierService()
    
    async def execute_gmail_to_classifier_workflow(
        self, 
        gmail_node_id: UUID, 
        session: AsyncSession,
        max_emails: int = 10
    ) -> Dict[str, Any]:
        """
        Execute complete Gmail-to-Classifier workflow with full persistence.
        
        Args:
            gmail_node_id: UUID of the Gmail node
            session: Database session
            max_emails: Maximum emails to process in one run
            
        Returns:
            Dictionary with workflow results
        """
        workflow_execution = None
        start_time = datetime.now(timezone.utc)
        
        try:
            workflow_execution = WorkflowExecution(
                id=uuid4(),
                workflow_type="gmail_to_classifier",
                execution_status="running",
                gmail_node_id=gmail_node_id,
                input_data={"max_emails": max_emails},
                started_at=start_time
            )
            session.add(workflow_execution)
            await session.commit()
            await session.refresh(workflow_execution)
            
            # 2. Verify Gmail node exists and is active
            gmail_node = await session.get(GmailNode, gmail_node_id)
            if not gmail_node:
                raise ValueError(f"Gmail node {gmail_node_id} not found")
            
            if not gmail_node.is_active:
                raise ValueError(f"Gmail node '{gmail_node.name}' is not active")
            
            # 3. Get unprocessed emails
            unprocessed_emails = await self._get_unprocessed_emails(
                gmail_node_id, session, max_emails
            )
            
            if not unprocessed_emails:
                # No emails to process - mark as completed
                await self._complete_workflow(
                    workflow_execution, session, 
                    output_data={
                        "message": "No unprocessed emails found",
                        "emails_processed": 0,
                        "classifications": []
                    }
                )
                return {
                    "workflow_id": str(workflow_execution.id),
                    "gmail_node": gmail_node.name,
                    "status": "completed",
                    "emails_found": 0,
                    "emails_processed": 0,
                    "classifications": []
                }
            
            # 4. Process each email through classifier
            results = await self._process_emails_batch(
                unprocessed_emails, workflow_execution, session
            )
            
            # 5. Complete workflow execution
            await self._complete_workflow(workflow_execution, session, results)
            
            return {
                "workflow_id": str(workflow_execution.id),
                "gmail_node": gmail_node.name,
                "status": "completed",
                "emails_found": len(unprocessed_emails),
                "emails_processed": results["emails_processed"],
                "emails_failed": results["emails_failed"],
                "classifications": results["classifications"],
                "execution_time_ms": results["execution_time_ms"]
            }
            
        except Exception as e:
            # Mark workflow as failed
            if workflow_execution:
                await self._fail_workflow(workflow_execution, session, str(e))
            raise
    
    async def _get_unprocessed_emails(
        self, 
        gmail_node_id: UUID, 
        session: AsyncSession, 
        limit: int
    ) -> List[RawEmail]:
        """Get unprocessed emails for a Gmail node."""
        
        result = await session.execute(
            select(RawEmail)
            .where(
                RawEmail.gmail_node_id == gmail_node_id,
                RawEmail.is_processed == False
            )
            .order_by(RawEmail.received_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def _process_emails_batch(
        self, 
        emails: List[RawEmail], 
        workflow_execution: WorkflowExecution,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Process a batch of emails through the classifier."""
        
        classifications = []
        emails_processed = 0
        emails_failed = 0
        
        for email in emails:
            try:
                # Process single email
                classification = await self._process_single_email(
                    email, workflow_execution, session
                )
                if classification:
                    classifications.append(classification)
                    emails_processed += 1
                else:
                    emails_failed += 1
                    
            except Exception as e:
                emails_failed += 1
                # Mark email as failed
                await self._mark_email_failed(email, session, str(e))
        
        # Calculate execution time
        execution_time_ms = int(
            (datetime.now(timezone.utc) - workflow_execution.started_at).total_seconds() * 1000
        )
        
        return {
            "emails_processed": emails_processed,
            "emails_failed": emails_failed,
            "classifications": classifications,
            "execution_time_ms": execution_time_ms
        }
    
    async def _process_single_email(
        self, 
        raw_email: RawEmail, 
        workflow_execution: WorkflowExecution,
        session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Process a single email through the classifier with full persistence."""
        
        try:
            # 1. Create envelope for classifier
            envelope_data = EnvelopeData(
                subject=raw_email.subject,
                body=raw_email.body
            )
            envelope = EnvelopeIn(data=envelope_data)
            
            # 2. Classify email using the classifier service
            classification_result = await self.classifier_service.classify_from_envelope(
                envelope, session
            )
            
            # 3. Get the created EmailRecord to link it properly
            # Find the most recent EmailRecord (the one we just created)
            latest_record_result = await session.execute(
                select(EmailRecord)
                .where(
                    EmailRecord.subject == raw_email.subject,
                    EmailRecord.body == raw_email.body
                )
                .order_by(EmailRecord.created_at.desc())
                .limit(1)
            )
            email_record = latest_record_result.scalar_one_or_none()
            
            if email_record:
                # 4. Link EmailRecord to RawEmail
                await session.execute(
                    update(EmailRecord)
                    .where(EmailRecord.id == email_record.id)
                    .values(raw_email_id=raw_email.id)
                )
                
                # 5. Update workflow execution with email record link
                await session.execute(
                    update(WorkflowExecution)
                    .where(WorkflowExecution.id == workflow_execution.id)
                    .values(
                        raw_email_id=raw_email.id,
                        email_record_id=email_record.id
                    )
                )
            
            # 6. Mark raw email as processed
            await session.execute(
                update(RawEmail)
                .where(RawEmail.id == raw_email.id)
                .values(
                    is_processed=True,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            
            await session.commit()
            
            # 7. Return classification data
            return {
                "email_id": str(raw_email.id),
                "from": raw_email.from_address,
                "subject": raw_email.subject,
                "priority": classification_result.priority,
                "label": classification_result.label,
                "summary": classification_result.summary,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            # Mark email as failed
            await self._mark_email_failed(raw_email, session, str(e))
            raise
    
    async def _mark_email_failed(
        self, 
        raw_email: RawEmail, 
        session: AsyncSession, 
        error_message: str
    ) -> None:
        """Mark an email as failed with error details."""
        
        await session.execute(
            update(RawEmail)
            .where(RawEmail.id == raw_email.id)
            .values(
                is_processed=True,  # Mark as processed even though it failed
                processing_error=error_message,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()
    
    async def _complete_workflow(
        self, 
        workflow_execution: WorkflowExecution, 
        session: AsyncSession,
        output_data: Dict[str, Any]
    ) -> None:
        """Mark workflow execution as completed."""
        
        execution_time_ms = int(
            (datetime.now(timezone.utc) - workflow_execution.started_at).total_seconds() * 1000
        )
        
        await session.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == workflow_execution.id)
            .values(
                execution_status="completed",
                output_data=output_data,
                execution_time_ms=execution_time_ms,
                completed_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()
    
    async def _fail_workflow(
        self, 
        workflow_execution: WorkflowExecution, 
        session: AsyncSession,
        error_message: str
    ) -> None:
        """Mark workflow execution as failed."""
        
        execution_time_ms = int(
            (datetime.now(timezone.utc) - workflow_execution.started_at).total_seconds() * 1000
        )
        
        await session.execute(
            update(WorkflowExecution)
            .where(WorkflowExecution.id == workflow_execution.id)
            .values(
                execution_status="failed",
                error_message=error_message,
                execution_time_ms=execution_time_ms,
                completed_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()
    
    async def get_workflow_execution(
        self, 
        execution_id: UUID, 
        session: AsyncSession
    ) -> Optional[WorkflowExecution]:
        """Get workflow execution with related data."""
        
        result = await session.execute(
            select(WorkflowExecution)
            .options(
                selectinload(WorkflowExecution.gmail_node),
                selectinload(WorkflowExecution.raw_email),
                selectinload(WorkflowExecution.email_record)
            )
            .where(WorkflowExecution.id == execution_id)
        )
        return result.scalar_one_or_none()
    
    async def list_workflow_executions(
        self, 
        session: AsyncSession,
        gmail_node_id: Optional[UUID] = None,
        limit: int = 50
    ) -> List[WorkflowExecution]:
        """List workflow executions with optional filtering."""
        
        query = select(WorkflowExecution)
        
        if gmail_node_id:
            query = query.where(WorkflowExecution.gmail_node_id == gmail_node_id)
        
        query = query.order_by(WorkflowExecution.started_at.desc()).limit(limit)
        
        result = await session.execute(query)
        return result.scalars().all()