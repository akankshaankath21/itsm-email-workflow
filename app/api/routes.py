from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import (
    # Gmail schemas
    GmailNodeConfigIn, GmailNodeOut, GmailNodeStatusOut, 
    RawEmailOut, SuccessResponse,
    # Existing mail classifier schemas
    EnvelopeIn, ExecuteResponse
)
from app.controllers.gmail_controller import GmailController
from app.controllers.mail_controller import MailController

# Create router
router = APIRouter()

# Initialize controllers
gmail_controller = GmailController()
mail_controller = MailController()


@router.post("/gmail-nodes", response_model=GmailNodeOut, tags=["Gmail Nodes"])
async def create_gmail_node(
    config: GmailNodeConfigIn,
    session: AsyncSession = Depends(get_session)
) -> GmailNodeOut:
    """Create a new Gmail trigger node."""
    try:
        return await gmail_controller.create_gmail_node(config, session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@router.get("/gmail-nodes", response_model=List[GmailNodeOut], tags=["Gmail Nodes"])
async def list_gmail_nodes(
    active_only: bool = Query(False, description="Only return active nodes"),
    session: AsyncSession = Depends(get_session)
) -> List[GmailNodeOut]:
    """List all Gmail nodes."""
    try:
        return await gmail_controller.list_gmail_nodes(session, active_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gmail-nodes/{node_id}", response_model=GmailNodeOut, tags=["Gmail Nodes"])
async def get_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> GmailNodeOut:
    """Get a specific Gmail node by ID."""
    try:
        return await gmail_controller.get_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/gmail-nodes/{node_id}/start", response_model=SuccessResponse, tags=["Gmail Nodes"])
async def start_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> SuccessResponse:
    """Start Gmail node monitoring."""
    try:
        return await gmail_controller.start_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/gmail-nodes/{node_id}/stop", response_model=SuccessResponse, tags=["Gmail Nodes"])
async def stop_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> SuccessResponse:
    """Stop Gmail node monitoring."""
    try:
        return await gmail_controller.stop_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/gmail-nodes/{node_id}/restart", response_model=SuccessResponse, tags=["Gmail Nodes"])
async def restart_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> SuccessResponse:
    """Restart Gmail node (stop then start)."""
    try:
        return await gmail_controller.restart_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gmail-nodes/{node_id}/status", response_model=GmailNodeStatusOut, tags=["Gmail Nodes"])
async def get_gmail_node_status(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> GmailNodeStatusOut:
    """Get detailed Gmail node status with recent emails."""
    try:
        return await gmail_controller.get_gmail_node_status(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gmail-nodes/{node_id}/emails", response_model=List[RawEmailOut], tags=["Gmail Nodes"])
async def get_gmail_node_emails(
    node_id: UUID,
    limit: int = Query(50, ge=1, le=100, description="Number of emails to return"),
    processed_only: bool = Query(False, description="Only return processed emails"),
    session: AsyncSession = Depends(get_session)
) -> List[RawEmailOut]:
    """Get raw emails processed by a Gmail node."""
    try:
        return await gmail_controller.get_gmail_node_emails(
            node_id, session, limit, processed_only
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @router.get("/gmail-nodes/{node_id}/statistics", tags=["Gmail Nodes"])
# async def get_gmail_node_statistics(
#     node_id: UUID,
#     session: AsyncSession = Depends(get_session)
# ) -> dict:
#     """Get Gmail node processing statistics."""
#     try:
#         return await gmail_controller.get_gmail_node_statistics(node_id, session)
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/gmail-nodes/{node_id}/check", tags=["Gmail Nodes"])
# async def manual_email_check(
#     node_id: UUID,
#     session: AsyncSession = Depends(get_session)
# ) -> dict:
#     """Manually trigger an email check for a Gmail node."""
#     try:
#         return await gmail_controller.manual_email_check(node_id, session)
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@router.delete("/gmail-nodes/{node_id}", response_model=SuccessResponse, tags=["Gmail Nodes"])
async def delete_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> SuccessResponse:
    """Delete Gmail node and stop monitoring."""
    try:
        return await gmail_controller.delete_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nodes/mail-classifier/execute", response_model=ExecuteResponse, tags=["Mail Classifier"])
async def execute_mail_classifier(
    envelope: EnvelopeIn, 
    session: AsyncSession = Depends(get_session)
) -> ExecuteResponse:
    """Execute mail classifier node on email data."""
    try:
        return await mail_controller.execute_from_envelope(envelope, session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
from app.services.workflow_service import WorkflowService

# Initialize workflow service
workflow_service = WorkflowService()

@router.post("/workflows/gmail-to-classifier/{node_id}", tags=["Workflows"])
async def execute_gmail_to_classifier_workflow(
    node_id: UUID,
    max_emails: int = Query(10, ge=1, le=50, description="Maximum emails to process"),
    session: AsyncSession = Depends(get_session)
) -> dict:
    """
    Execute Gmail-to-Classifier workflow with full database persistence.
    
    This workflow:
    1. Gets unprocessed emails from Gmail node
    2. Classifies each email using AI
    3. Links classifications to original emails
    4. Marks emails as processed
    5. Creates workflow execution record
    """
    try:
        return await workflow_service.execute_gmail_to_classifier_workflow(
            node_id, session, max_emails
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")

@router.get("/workflows/executions/{execution_id}", tags=["Workflows"])
async def get_workflow_execution(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Get detailed information about a workflow execution."""
    try:
        execution = await workflow_service.get_workflow_execution(execution_id, session)
        if not execution:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        return {
            "id": str(execution.id),
            "workflow_type": execution.workflow_type,
            "status": execution.execution_status,
            "started_at": execution.started_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "execution_time_ms": execution.execution_time_ms,
            "input_data": execution.input_data,
            "output_data": execution.output_data,
            "error_message": execution.error_message,
            "gmail_node_id": str(execution.gmail_node_id) if execution.gmail_node_id else None,
            "raw_email_id": str(execution.raw_email_id) if execution.raw_email_id else None,
            "email_record_id": str(execution.email_record_id) if execution.email_record_id else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/workflows/executions", tags=["Workflows"])
async def list_workflow_executions(
    gmail_node_id: Optional[UUID] = Query(None, description="Filter by Gmail node ID"),
    limit: int = Query(50, ge=1, le=100, description="Number of executions to return"),
    session: AsyncSession = Depends(get_session)
) -> dict:
    """List workflow executions with optional filtering."""
    try:
        executions = await workflow_service.list_workflow_executions(
            session, gmail_node_id, limit
        )
        
        return {
            "executions": [
                {
                    "id": str(execution.id),
                    "workflow_type": execution.workflow_type,
                    "status": execution.execution_status,
                    "started_at": execution.started_at.isoformat(),
                    "execution_time_ms": execution.execution_time_ms,
                    "gmail_node_id": str(execution.gmail_node_id) if execution.gmail_node_id else None
                }
                for execution in executions
            ],
            "total": len(executions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/workflows/status", tags=["Workflows"])
async def get_workflow_status(
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Get overall workflow system status."""
    try:
        # Get Gmail nodes status
        gmail_nodes = await gmail_controller.list_gmail_nodes(session)
        active_gmail_nodes = [node for node in gmail_nodes if node.is_active]
        
        # Calculate total emails processed
        total_emails = sum(node.emails_processed for node in gmail_nodes)
        
        return {
            "system_status": "operational",
            "gmail_nodes": {
                "total": len(gmail_nodes),
                "active": len(active_gmail_nodes),
                "total_emails_processed": total_emails
            },
            "mail_classifier": {
                "status": "available"
            },
            "timestamp": "2025-08-14T12:00:00Z"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health", tags=["System"])
async def health_check() -> dict:
    """System health check."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "gmail_nodes": "operational",
            "mail_classifier": "operational", 
            "database": "operational"
        },
        "timestamp": "2025-08-14T12:00:00Z"
    }