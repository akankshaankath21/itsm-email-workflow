import asyncio
import base64
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, desc
from sqlalchemy.orm import selectinload

from app.models import GmailNode, RawEmail, WorkflowExecution
from app.schemas import (
    GmailNodeConfigIn, GmailNodeOut, GmailNodeStatusOut, 
    RawEmailOut, RawEmailSummary, SuccessResponse
)
from app.nodes.gmail_trigger import GmailTriggerNode

class GmailService:
    """Service layer for Gmail trigger node operations."""
    
    def __init__(self):
        self.active_polling_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_gmail_node(
        self, 
        config: GmailNodeConfigIn, 
        session: AsyncSession
    ) -> GmailNodeOut:
        """Create a new Gmail node configuration in database."""
        
        # Create database record
        gmail_node = GmailNode(
            id=uuid4(),
            name=config.name,
            email_address=config.email_address,
            credentials_file_path=config.credentials_file_path,
            token_file_path=config.token_file_path,
            filter_sender=config.filter_sender,
            filter_subject_contains=config.filter_subject_contains,
            only_unread=config.only_unread,
            mark_as_read=config.mark_as_read,
            polling_interval=config.polling_interval,
            max_results=config.max_results,
            is_active=False,
            emails_processed=0
        )
        
        session.add(gmail_node)
        await session.commit()
        await session.refresh(gmail_node)
        
        return GmailNodeOut.model_validate(gmail_node)
    
    async def get_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> Optional[GmailNodeOut]:
        """Get Gmail node by ID."""
        
        result = await session.execute(
            select(GmailNode).where(GmailNode.id == node_id)
        )
        gmail_node = result.scalar_one_or_none()
        
        if not gmail_node:
            return None
            
        return GmailNodeOut.model_validate(gmail_node)
    
    async def list_gmail_nodes(
        self, 
        session: AsyncSession,
        active_only: bool = False
    ) -> List[GmailNodeOut]:
        """List all Gmail nodes."""
        
        query = select(GmailNode)
        if active_only:
            query = query.where(GmailNode.is_active == True)
            
        query = query.order_by(desc(GmailNode.created_at))
        
        result = await session.execute(query)
        gmail_nodes = result.scalars().all()
        
        return [GmailNodeOut.model_validate(node) for node in gmail_nodes]
    
    async def start_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """Start Gmail node monitoring."""
        
        # Get node from database
        result = await session.execute(
            select(GmailNode).where(GmailNode.id == node_id)
        )
        gmail_node = result.scalar_one_or_none()
        
        if not gmail_node:
            raise ValueError(f"Gmail node {node_id} not found")
        
        if gmail_node.is_active:
            return SuccessResponse(
                message=f"Gmail node '{gmail_node.name}' is already active"
            )
        
        # Create and start the actual Gmail trigger node
        trigger_node = GmailTriggerNode(
            node_id=str(node_id),
            name=gmail_node.name,
            email_address=gmail_node.email_address,
            credentials_file_path=gmail_node.credentials_file_path,
            token_file_path=gmail_node.token_file_path,
            filter_sender=gmail_node.filter_sender,
            filter_subject_contains=gmail_node.filter_subject_contains,
            only_unread=gmail_node.only_unread,
            mark_as_read=gmail_node.mark_as_read,
            polling_interval=gmail_node.polling_interval,
            max_results=gmail_node.max_results
        )
        
        # Start the node (this handles OAuth and Gmail API setup)
        success = await trigger_node.start()
        if not success:
            raise RuntimeError(f"Failed to start Gmail node '{gmail_node.name}'")
        
        # Update database status
        await session.execute(
            update(GmailNode)
            .where(GmailNode.id == node_id)
            .values(is_active=True, last_checked=datetime.now(timezone.utc))
        )
        await session.commit()
        
        # Start background polling task
        task = asyncio.create_task(
            self._polling_loop(trigger_node, session, node_id)
        )
        self.active_polling_tasks[str(node_id)] = task
        
        return SuccessResponse(
            message=f"Gmail node '{gmail_node.name}' started successfully"
        )
    
    async def stop_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """Stop Gmail node monitoring."""
        
        # Stop polling task
        task_key = str(node_id)
        if task_key in self.active_polling_tasks:
            task = self.active_polling_tasks[task_key]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.active_polling_tasks[task_key]
        
        # Update database status
        await session.execute(
            update(GmailNode)
            .where(GmailNode.id == node_id)
            .values(is_active=False)
        )
        await session.commit()
        
        return SuccessResponse(
            message=f"Gmail node stopped successfully"
        )
    
    async def get_gmail_node_status(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> Optional[GmailNodeStatusOut]:
        """Get detailed Gmail node status with recent emails."""
        
        # Get node with recent emails
        result = await session.execute(
            select(GmailNode)
            .options(selectinload(GmailNode.raw_emails))
            .where(GmailNode.id == node_id)
        )
        gmail_node = result.scalar_one_or_none()
        
        if not gmail_node:
            return None
        
        # Get recent emails (last 5)
        recent_emails_result = await session.execute(
            select(RawEmail)
            .where(RawEmail.gmail_node_id == node_id)
            .order_by(desc(RawEmail.received_at))
            .limit(5)
        )
        recent_emails = recent_emails_result.scalars().all()
        
        # Build active filters list
        active_filters = []
        if gmail_node.filter_sender:
            active_filters.append(f"Sender: {gmail_node.filter_sender}")
        if gmail_node.filter_subject_contains:
            active_filters.append(f"Subject contains: {gmail_node.filter_subject_contains}")
        if gmail_node.only_unread:
            active_filters.append("Unread emails only")
        
        return GmailNodeStatusOut(
            id=gmail_node.id,
            name=gmail_node.name,
            email_address=gmail_node.email_address,
            is_active=gmail_node.is_active,
            emails_processed=gmail_node.emails_processed,
            last_checked=gmail_node.last_checked,
            last_email_received=gmail_node.last_email_received,
            polling_interval=gmail_node.polling_interval,
            active_filters=active_filters,
            recent_emails=[
                RawEmailSummary.model_validate(email) for email in recent_emails
            ]
        )
    
    async def get_raw_emails(
        self, 
        node_id: UUID, 
        session: AsyncSession,
        limit: int = 50,
        processed_only: bool = False
    ) -> List[RawEmailOut]:
        """Get raw emails for a Gmail node."""
        
        query = select(RawEmail).where(RawEmail.gmail_node_id == node_id)
        
        if processed_only:
            query = query.where(RawEmail.is_processed == True)
            
        query = query.order_by(desc(RawEmail.received_at)).limit(limit)
        
        result = await session.execute(query)
        raw_emails = result.scalars().all()
        
        return [RawEmailOut.model_validate(email) for email in raw_emails]
    
    async def delete_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """Delete Gmail node and stop monitoring."""
        
        # Stop the node first
        await self.stop_gmail_node(node_id, session)
        
        # Delete from database (cascade will handle related emails)
        await session.execute(
            update(GmailNode)
            .where(GmailNode.id == node_id)
            .values(is_active=False)
        )
        
        # In production, you might want to soft delete instead
        # For now, we'll just deactivate
        await session.commit()
        
        return SuccessResponse(
            message="Gmail node deleted successfully"
        )
    
    async def _polling_loop(
        self, 
        trigger_node: "GmailTriggerNode", 
        session: AsyncSession,
        node_id: UUID
    ) -> None:
        """Background polling loop for a Gmail node."""
        
        try:
            while True:
                try:
                    # Execute one polling cycle
                    new_emails = await trigger_node.execute_once()
                    
                    if new_emails:
                        # Save new emails to database
                        await self._save_new_emails(new_emails, node_id, session)
                        
                        # Update node statistics
                        await session.execute(
                            update(GmailNode)
                            .where(GmailNode.id == node_id)
                            .values(
                                emails_processed=GmailNode.emails_processed + len(new_emails),
                                last_checked=datetime.now(timezone.utc),
                                last_email_received=datetime.now(timezone.utc)
                            )
                        )
                    else:
                        # Update last checked time
                        await session.execute(
                            update(GmailNode)
                            .where(GmailNode.id == node_id)
                            .values(last_checked=datetime.now(timezone.utc))
                        )
                    
                    await session.commit()
                    
                    # Wait for next polling cycle
                    await asyncio.sleep(trigger_node.polling_interval)
                    
                except Exception as e:
                    print(f"Error in polling loop for node {node_id}: {str(e)}")
                    await asyncio.sleep(60)  # Wait 1 minute before retrying
                    
        except asyncio.CancelledError:
            # Clean shutdown
            await trigger_node.stop()
            raise
    
    async def _save_new_emails(
        self, 
        emails: List[Dict[str, Any]], 
        node_id: UUID, 
        session: AsyncSession
    ) -> None:
        """Save new emails to database."""
        
        for email_data in emails:
            # Check if email already exists (prevent duplicates)
            existing = await session.execute(
                select(RawEmail).where(
                    RawEmail.gmail_message_id == email_data['id']
                )
            )
            if existing.scalar_one_or_none():
                continue  # Skip duplicate
            
            # Create new raw email record
            raw_email = RawEmail(
                id=uuid4(),
                gmail_message_id=email_data['id'],
                gmail_thread_id=email_data.get('thread_id', ''),
                from_address=email_data.get('from', ''),
                to_address=email_data.get('to', ''),
                cc_address=email_data.get('cc'),
                bcc_address=email_data.get('bcc'),
                subject=email_data.get('subject'),
                body=email_data.get('body', ''),
                snippet=email_data.get('snippet'),
                received_at=datetime.fromisoformat(email_data['received_at'].replace('Z', '+00:00')),
                is_read=email_data.get('is_read', False),
                labels=email_data.get('labels', []),
                size_estimate=email_data.get('size_estimate'),
                is_processed=False,
                gmail_node_id=node_id
            )
            
            session.add(raw_email)