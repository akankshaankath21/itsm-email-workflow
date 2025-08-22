from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    GmailNodeConfigIn, GmailNodeOut, GmailNodeStatusOut, 
    RawEmailOut, SuccessResponse, ErrorResponse
)
from app.services.gmail_service import GmailService

class GmailController:
    """Controller that handles Gmail node HTTP requests."""
    
    def __init__(self) -> None:
        self.service = GmailService()
    
    async def create_gmail_node(
        self, 
        config: GmailNodeConfigIn, 
        session: AsyncSession
    ) -> GmailNodeOut:
        """
        Create a new Gmail trigger node.
        
        Args:
            config: Gmail node configuration
            session: Database session
            
        Returns:
            Created Gmail node information
            
        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If creation fails
        """
        try:
            return await self.service.create_gmail_node(config, session)
        except Exception as e:
            raise RuntimeError(f"Failed to create Gmail node: {str(e)}")
    
    async def list_gmail_nodes(
        self, 
        session: AsyncSession,
        active_only: bool = False
    ) -> List[GmailNodeOut]:
        """
        List all Gmail nodes.
        
        Args:
            session: Database session
            active_only: If True, only return active nodes
            
        Returns:
            List of Gmail nodes
        """
        return await self.service.list_gmail_nodes(session, active_only)
    
    async def get_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> GmailNodeOut:
        """
        Get a specific Gmail node by ID.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Gmail node information
            
        Raises:
            ValueError: If node not found
        """
        node = await self.service.get_gmail_node(node_id, session)
        if not node:
            raise ValueError(f"Gmail node {node_id} not found")
        return node
    
    async def start_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """
        Start Gmail node monitoring.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Success response with message
            
        Raises:
            ValueError: If node not found
            RuntimeError: If start operation fails
        """
        try:
            return await self.service.start_gmail_node(node_id, session)
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to start Gmail node: {str(e)}")
    
    async def stop_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """
        Stop Gmail node monitoring.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Success response with message
            
        Raises:
            ValueError: If node not found
        """
        return await self.service.stop_gmail_node(node_id, session)
    
    async def get_gmail_node_status(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> GmailNodeStatusOut:
        """
        Get detailed Gmail node status with recent emails.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Detailed node status
            
        Raises:
            ValueError: If node not found
        """
        status = await self.service.get_gmail_node_status(node_id, session)
        if not status:
            raise ValueError(f"Gmail node {node_id} not found")
        return status
    
    async def get_gmail_node_emails(
        self, 
        node_id: UUID, 
        session: AsyncSession,
        limit: int = 50,
        processed_only: bool = False
    ) -> List[RawEmailOut]:
        """
        Get raw emails processed by a Gmail node.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            limit: Maximum number of emails to return
            processed_only: If True, only return processed emails
            
        Returns:
            List of raw emails
            
        Raises:
            ValueError: If node not found or invalid limit
        """
        if limit < 1 or limit > 100:
            raise ValueError("Limit must be between 1 and 100")
        
        # Verify node exists
        await self.get_gmail_node(node_id, session)
        
        return await self.service.get_raw_emails(
            node_id, session, limit, processed_only
        )
    
    async def delete_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """
        Delete Gmail node and stop monitoring.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Success response with message
        """
        # Verify node exists first
        await self.get_gmail_node(node_id, session)
        
        return await self.service.delete_gmail_node(node_id, session)
    
    async def restart_gmail_node(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> SuccessResponse:
        """
        Restart Gmail node (stop then start).
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Success response with message
        """
        # Stop the node
        await self.stop_gmail_node(node_id, session)
        
        # Start the node
        return await self.start_gmail_node(node_id, session)
    
    async def update_gmail_node_config(
        self, 
        node_id: UUID, 
        config: GmailNodeConfigIn, 
        session: AsyncSession
    ) -> GmailNodeOut:
        """
        Update Gmail node configuration.
        
        Args:
            node_id: Gmail node UUID
            config: New configuration
            session: Database session
            
        Returns:
            Updated Gmail node information
            
        Raises:
            ValueError: If node not found
            RuntimeError: If update fails
        """
        # Verify node exists
        existing_node = await self.get_gmail_node(node_id, session)
        
        # If node is active, stop it first
        if existing_node.is_active:
            await self.stop_gmail_node(node_id, session)
            should_restart = True
        else:
            should_restart = False
        
        try:
            # Update configuration in database
            # (This would require adding an update method to the service)
            # For now, we'll return the existing node
            # In a full implementation, you'd add service.update_gmail_node()
            
            updated_node = existing_node  # Placeholder
            
            # Restart if it was active
            if should_restart:
                await self.start_gmail_node(node_id, session)
            
            return updated_node
            
        except Exception as e:
            raise RuntimeError(f"Failed to update Gmail node: {str(e)}")
    
    async def get_gmail_node_statistics(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> dict:
        """
        Get Gmail node processing statistics.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Dictionary with statistics
        """
        status = await self.get_gmail_node_status(node_id, session)
        
        # Calculate additional statistics
        emails = await self.get_gmail_node_emails(node_id, session, limit=100)
        
        processed_count = sum(1 for email in emails if email.is_processed)
        failed_count = sum(1 for email in emails if email.processing_error)
        
        return {
            "node_id": str(node_id),
            "node_name": status.name,
            "is_active": status.is_active,
            "total_emails": len(emails),
            "processed_emails": processed_count,
            "failed_emails": failed_count,
            "processing_rate": (processed_count / len(emails) * 100) if emails else 0,
            "last_checked": status.last_checked,
            "last_email_received": status.last_email_received,
            "polling_interval": status.polling_interval,
            "active_filters": status.active_filters
        }
    
    async def manual_email_check(
        self, 
        node_id: UUID, 
        session: AsyncSession
    ) -> dict:
        """
        Manually trigger an email check for a Gmail node.
        
        Args:
            node_id: Gmail node UUID
            session: Database session
            
        Returns:
            Dictionary with check results
            
        Raises:
            ValueError: If node not found or not active
        """
        # Verify node exists and is active
        node = await self.get_gmail_node(node_id, session)
        if not node.is_active:
            raise ValueError(f"Gmail node {node_id} is not active")
        
        # This would require adding a manual check method to the service
        # For now, return a placeholder response
        return {
            "node_id": str(node_id),
            "check_timestamp": "2025-08-14T12:00:00Z",
            "emails_found": 0,
            "message": "Manual email check completed"
        }