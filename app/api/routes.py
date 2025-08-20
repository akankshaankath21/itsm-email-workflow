
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import (
    # Gmail schemas
    GmailNodeConfigIn, GmailNodeOut, GmailNodeStatusOut, 
    RawEmailOut, SuccessResponse,
    # Mail classifier schemas
    EnvelopeIn, ExecuteResponse
)
from app.controllers.gmail_controller import GmailController
from app.controllers.mail_controller import MailController
from app.services.workflow_service import WorkflowService


router = APIRouter()


gmail_controller = GmailController()
mail_controller = MailController()
workflow_service = WorkflowService()


@router.post("/nodes/gmail", response_model=GmailNodeOut, tags=["1. Core Nodes"])
async def create_gmail_node(
    config: GmailNodeConfigIn,
    session: AsyncSession = Depends(get_session)
) -> GmailNodeOut:

    try:
        return await gmail_controller.create_gmail_node(config, session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@router.get("/nodes/gmail", response_model=List[GmailNodeOut], tags=["1. Core Nodes"])
async def list_gmail_nodes(
    active_only: bool = Query(False, description="Only return active Gmail nodes"),
    session: AsyncSession = Depends(get_session)
) -> List[GmailNodeOut]:

    try:
        return await gmail_controller.list_gmail_nodes(session, active_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/nodes/gmail/{node_id}", response_model=GmailNodeOut, tags=["1. Core Nodes"])
async def get_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> GmailNodeOut:

    try:
        return await gmail_controller.get_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nodes/gmail/{node_id}/start", response_model=SuccessResponse, tags=["1. Core Nodes"])
async def start_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> SuccessResponse:

    try:
        return await gmail_controller.start_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nodes/gmail/{node_id}/stop", response_model=SuccessResponse, tags=["1. Core Nodes"])
async def stop_gmail_node(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> SuccessResponse:

    try:
        return await gmail_controller.stop_gmail_node(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/nodes/gmail/{node_id}/status", response_model=GmailNodeStatusOut, tags=["1. Core Nodes"])
async def get_gmail_node_status(
    node_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> GmailNodeStatusOut:

    try:
        return await gmail_controller.get_gmail_node_status(node_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/nodes/gmail/{node_id}/emails", response_model=List[RawEmailOut], tags=["1. Core Nodes"])
async def get_gmail_node_emails(
    node_id: UUID,
    limit: int = Query(50, ge=1, le=100, description="Number of emails to return"),
    processed_only: bool = Query(False, description="Only return processed emails"),
    session: AsyncSession = Depends(get_session)
) -> List[RawEmailOut]:

    try:
        return await gmail_controller.get_gmail_node_emails(
            node_id, session, limit, processed_only
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nodes/classifier/execute", response_model=ExecuteResponse, tags=["1. Core Nodes"])
async def execute_mail_classifier(
    envelope: EnvelopeIn, 
    session: AsyncSession = Depends(get_session)
) -> ExecuteResponse:

    try:
        return await mail_controller.execute_from_envelope(envelope, session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/workflows/static/gmail-to-classifier/{node_id}", tags=["2. Static Workflows"])
async def execute_gmail_to_classifier_workflow(
    node_id: UUID,
    max_emails: int = Query(10, ge=1, le=50, description="Maximum emails to process"),
    session: AsyncSession = Depends(get_session)
) -> dict:

    try:
        return await workflow_service.execute_gmail_to_classifier_workflow(
            node_id, session, max_emails
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")

@router.get("/workflows/static/executions/{execution_id}", tags=["2. Static Workflows"])
async def get_static_workflow_execution(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> dict:

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

@router.get("/workflows/static/executions", tags=["2. Static Workflows"])
async def list_static_workflow_executions(
    gmail_node_id: Optional[UUID] = Query(None, description="Filter by Gmail node ID"),
    limit: int = Query(50, ge=1, le=100, description="Number of executions to return"),
    session: AsyncSession = Depends(get_session)
) -> dict:

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



@router.get("/system/status", tags=["3. System Status"])
async def get_system_status(
    session: AsyncSession = Depends(get_session)
) -> dict:

    try:
        gmail_nodes = await gmail_controller.list_gmail_nodes(session)
        active_gmail_nodes = [node for node in gmail_nodes if node.is_active]
        total_emails = sum(node.emails_processed for node in gmail_nodes)
        
        return {
            "system_status": "operational",
            "timestamp": "2025-08-14T12:00:00Z",
            "components": {
                "gmail_nodes": {
                    "total": len(gmail_nodes),
                    "active": len(active_gmail_nodes),
                    "total_emails_processed": total_emails
                },
                "mail_classifier": {
                    "status": "available",
                    "provider": "azure_openai"
                },
                "database": "operational",
                "static_workflows": "available"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health", tags=["3. System Status"])
async def health_check() -> dict:

    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "api": "operational",
            "database": "operational",
            "workflows": "operational"
        }
    }