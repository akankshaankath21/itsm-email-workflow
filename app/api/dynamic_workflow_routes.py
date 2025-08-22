from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from app.db import get_session, async_session_factory
from app.services.dynamic_workflow_service import DynamicWorkflowService
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.workflow_models import WorkflowTemplate, WorkflowInstance

from app.services.gmail_service import GmailService

workflow_service = DynamicWorkflowService()
gmail_service = GmailService()

workflow_router = APIRouter(tags=["4. Dynamic Workflows"])

class CreateWorkflowTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    category: Optional[str] = Field(None, description="Workflow category (e.g., 'Email Processing')")

class AddNodeRequest(BaseModel):
    node_key: str = Field(min_length=1, max_length=100, description="Unique node identifier")
    node_type: str = Field(pattern="^(trigger|action)$", description="Node type: trigger or action")
    node_class: str = Field(min_length=1, max_length=255, description="Node class (e.g., GmailTriggerNode)")
    name: str = Field(min_length=1, max_length=255, description="Human-readable node name")
    description: Optional[str] = Field(None, description="Node description")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Node configuration")
    ui_position: Optional[Dict[str, Any]] = Field(None, description="UI position for drag-drop interface")

class AddEdgeRequest(BaseModel):
    source_node_key: str = Field(min_length=1, max_length=100, description="Source node key")
    target_node_key: str = Field(min_length=1, max_length=100, description="Target node key")
    data_mapping: Dict[str, str] = Field(default_factory=dict, description="How to map data between nodes")
    name: Optional[str] = Field(None, description="Edge name")

class ExecuteWorkflowRequest(BaseModel):
    trigger_data: Optional[Dict[str, Any]] = Field(None, description="Initial trigger data")
    triggered_by: str = Field(default="manual", description="Who/what triggered the workflow")

@workflow_router.post("/templates")
async def create_workflow_template(
    request: CreateWorkflowTemplateRequest,
    session: AsyncSession = Depends(get_session)
) -> Dict[str, str]:
    try:
        template = await workflow_service.create_workflow_template(
            name=request.name,
            description=request.description,
            category=request.category,
            session=session
        )
        
        return {
            "template_id": str(template.id),
            "name": template.name,
            "message": f"Workflow template '{template.name}' created successfully",
            "next_step": "Add nodes using POST /api/templates/{template_id}/nodes"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@workflow_router.get("/templates")
async def list_workflow_templates(
    active_only: bool = Query(True, description="Only return active templates"),
    category: Optional[str] = Query(None, description="Filter by category"),
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:

    try:
        templates = await workflow_service.list_workflow_templates(
            session=session,
            active_only=active_only,
            category=category
        )
        
        return [
            {
                "id": str(template.id),
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "is_active": template.is_active,
                "created_at": template.created_at.isoformat(),
                "total_nodes": len(template.nodes) if hasattr(template, 'nodes') else 0,
                "total_edges": len(template.edges) if hasattr(template, 'edges') else 0,
                "status": "Ready to execute" if (hasattr(template, 'nodes') and len(template.nodes) > 0) else "Empty template"
            }
            for template in templates
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.get("/templates/{template_id}")
async def get_workflow_template(
    template_id: UUID,
    include_details: bool = Query(True, description="Include nodes and edges"),
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:

    try:
        template = await workflow_service.get_workflow_template(template_id, session)
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        response = {
            "id": str(template.id),
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "is_active": template.is_active,
            "created_at": template.created_at.isoformat(),
            "total_nodes": len(template.nodes),
            "total_edges": len(template.edges),
            "workflow_structure": "DAG (Directed Acyclic Graph)"
        }
        
        if include_details:
            response["nodes"] = [
                {
                    "id": str(node.id),
                    "node_key": node.node_key,
                    "node_type": node.node_type,
                    "node_class": node.node_class,
                    "name": node.name,
                    "description": node.description,
                    "configuration": node.configuration,
                    "ui_position": node.ui_position,
                    "is_enabled": node.is_enabled,
                    "role": "Data Source" if node.node_type == "trigger" else "Data Processor"
                }
                for node in template.nodes
            ]
            
            response["edges"] = [
                {
                    "id": str(edge.id),
                    "source_node_key": next((n.node_key for n in template.nodes if n.id == edge.source_node_id), "unknown"),
                    "target_node_key": next((n.node_key for n in template.nodes if n.id == edge.target_node_id), "unknown"),
                    "data_mapping": edge.data_mapping,
                    "is_enabled": edge.is_enabled,
                    "connection_type": "Data Flow"
                }
                for edge in template.edges
            ]
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.post("/templates/{template_id}/nodes")
async def add_node_to_workflow(
    template_id: UUID,
    request: AddNodeRequest,
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:

    try:
        node = await workflow_service.add_node_to_workflow(
            template_id=template_id,
            node_key=request.node_key,
            node_type=request.node_type,
            node_class=request.node_class,
            name=request.name,
            configuration=request.configuration,
            description=request.description,
            ui_position=request.ui_position,
            session=session
        )
        
        return {
            "node_id": str(node.id),
            "node_key": node.node_key,
            "node_type": node.node_type,
            "node_class": node.node_class,
            "message": f"Node '{node.name}' added successfully",
            "next_step": "Connect to other nodes using POST /api/templates/{template_id}/edges"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.post("/templates/{template_id}/edges")
async def add_edge_to_workflow(
    template_id: UUID,
    request: AddEdgeRequest,
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:

    try:
        edge = await workflow_service.add_edge_to_workflow(
            template_id=template_id,
            source_node_key=request.source_node_key,
            target_node_key=request.target_node_key,
            data_mapping=request.data_mapping,
            name=request.name,
            session=session
        )
        
        return {
            "edge_id": str(edge.id),
            "source_node": request.source_node_key,
            "target_node": request.target_node_key,
            "data_mapping": request.data_mapping,
            "message": f"Connection created: {request.source_node_key} → {request.target_node_key}",
            "next_step": "Execute workflow using POST /api/templates/{template_id}/execute"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.post("/templates/{template_id}/execute")
async def execute_workflow(
    template_id: UUID,
    request: ExecuteWorkflowRequest,
    session: AsyncSession = Depends(get_session)
) -> Dict[str, str]:
    try:
        instance_id = await workflow_service.execute_workflow_template(
            template_id=template_id,
            trigger_data=request.trigger_data,
            triggered_by=request.triggered_by,
            session=session
        )
        
        return {
            "instance_id": str(instance_id),
            "template_id": str(template_id),
            "status": "execution_started",
            "message": "Dynamic workflow execution started successfully",
            "next_step": f"Monitor progress using GET /api/instances/{instance_id}/status"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.get("/instances/{instance_id}/status")
async def get_workflow_instance_status(
    instance_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:

    try:
        status = await workflow_service.get_workflow_instance_status(instance_id, session)
        if not status:
            raise HTTPException(status_code=404, detail="Workflow instance not found")
        
        status["execution_insights"] = {
            "total_nodes": len(status.get("nodes", [])),
            "completed_nodes": len([n for n in status.get("nodes", []) if n.get("status") == "completed"]),
            "failed_nodes": len([n for n in status.get("nodes", []) if n.get("status") == "failed"]),
            "execution_type": "DAG (Directed Acyclic Graph)",
            "engine": "Dynamic Workflow Execution Engine"
        }
        
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.get("/instances")
async def list_workflow_instances(
    template_id: Optional[UUID] = Query(None, description="Filter by template ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of instances to return"),
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:

    try:
        instances = await workflow_service.list_workflow_instances(
            session=session,
            template_id=template_id,
            status=status,
            limit=limit
        )
        
        return [
            {
                "instance_id": str(instance.id),
                "template_id": str(instance.workflow_template_id),
                "template_name": instance.workflow_template.name if hasattr(instance, 'workflow_template') else "Unknown",
                "status": instance.status,
                "started_at": instance.started_at.isoformat() if instance.started_at else None,
                "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
                "triggered_by": instance.triggered_by,
                "error_message": instance.error_message,
                "execution_type": "Dynamic DAG"
            }
            for instance in instances
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.get("/node-types")
async def get_available_node_types(
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:

    try:
        existing_gmail_nodes = await gmail_service.list_gmail_nodes(session)
        
        node_types = []
        
        for gmail_node in existing_gmail_nodes:
            node_types.append({
                "class_name": "GmailTriggerNode",
                "type": "trigger",
                "category": "Email Sources",
                "name": f"Gmail Monitor ({gmail_node.email_address})",
                "description": f"Monitors {gmail_node.email_address} for new emails",
                "gmail_node_id": str(gmail_node.id),
                "icon": "",
                "configuration_schema": {
                    "email_address": {
                        "type": "string", 
                        "required": True,
                        "default": gmail_node.email_address,
                        "readonly": True
                    },
                    "polling_interval": {
                        "type": "integer", 
                        "default": gmail_node.polling_interval,
                        "min": 5, "max": 3600,
                        "description": "How often to check for emails (seconds)"
                    },
                    "max_results": {
                        "type": "integer", 
                        "default": gmail_node.max_results,
                        "min": 1, "max": 100,
                        "description": "Maximum emails to fetch per check"
                    }
                },
                "output_schema": {
                    "emails": {
                        "type": "array", 
                        "description": "List of new emails from this Gmail account"
                    },
                    "emails_count": {
                        "type": "integer", 
                        "description": "Number of emails found"
                    }
                }
            })
        
        # Generic Gmail Trigger (for creating new Gmail monitors)
        node_types.append({
            "class_name": "GmailTriggerNode",
            "type": "trigger",
            "category": "Email Sources", 
            "name": "Gmail Monitor (New)",
            "description": "Create a new Gmail monitor for any email address",
            "icon": "",
            "configuration_schema": {
                "email_address": {
                    "type": "string", 
                    "required": True,
                    "description": "Gmail address to monitor"
                },
                "credentials_file_path": {
                    "type": "string", 
                    "required": True,
                    "description": "Path to Gmail credentials JSON file"
                },
                "polling_interval": {
                    "type": "integer", 
                    "default": 30,
                    "min": 5, "max": 3600
                },
                "max_results": {
                    "type": "integer", 
                    "default": 10,
                    "min": 1, "max": 100
                }
            },
            "output_schema": {
                "emails": {"type": "array", "description": "List of new emails"},
                "emails_count": {"type": "integer", "description": "Number of emails found"}
            }
        })
        
        # Email Classifier (uses existing classifier service)
        node_types.append({
            "class_name": "MailClassifierNode",
            "type": "action",
            "category": "AI Processing",
            "name": "Email Classifier",
            "description": "Classifies emails using AI (Priority, Label, Summary)",
            "icon": "",
            "configuration_schema": {
                "llm_model": {
                    "type": "string", 
                    "default": "gpt-4",
                    "options": ["gpt-4", "gpt-3.5-turbo"],
                    "description": "AI model to use for classification"
                }
            },
            "input_schema": {
                "input_emails": {
                    "type": "array", 
                    "required": True,
                    "description": "Array of emails to classify"
                }
            },
            "output_schema": {
                "classifications": {
                    "type": "array", 
                    "description": "Email classifications with priority, label, summary"
                }
            }
        })
        
        return {
            "node_types": node_types,
            "categories": {
                "Email Sources": "Nodes that fetch emails",
                "AI Processing": "Nodes that use AI to process data",
                "ITSM Integration": "Future: ServiceNow, Jira, etc."
            },
            "total_gmail_nodes": len(existing_gmail_nodes),
            "workflow_builder_info": {
                "engine": "DAG-based execution",
                "supports": ["drag-drop", "visual_connections", "real_time_monitoring"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.get("/gmail-nodes")
async def get_existing_gmail_nodes(
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:

    try:
        gmail_nodes = await gmail_service.list_gmail_nodes(session)
        
        return [
            {
                "id": str(node.id),
                "name": node.name,
                "email_address": node.email_address,
                "is_active": node.is_active,
                "polling_interval": node.polling_interval,
                "emails_processed": node.emails_processed,
                "last_checked": node.last_checked.isoformat() if node.last_checked else None,
                "can_use_in_workflow": True,
                "status": "Active" if node.is_active else "Inactive"
            }
            for node in gmail_nodes
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@workflow_router.get("/integration/status")
async def get_integration_status() -> Dict[str, Any]:
    """
    ✅ FIX: Removed session dependency to avoid context conflicts
    Each service call will use its own session
    """
    
    try:
        # ✅ Each service call creates its own session context
        async with async_session_factory() as session:
            # Check existing Gmail nodes
            gmail_nodes = await gmail_service.list_gmail_nodes(session)
            active_gmail_nodes = [node for node in gmail_nodes if node.is_active]
            
            # Check existing templates with eager loading
            templates_query = select(WorkflowTemplate).options(
                selectinload(WorkflowTemplate.nodes),
                selectinload(WorkflowTemplate.edges)
            ).order_by(WorkflowTemplate.created_at.desc())
            
            templates_result = await session.execute(templates_query)
            templates = templates_result.scalars().all()
            
            # Check existing instances with eager loading
            instances_query = select(WorkflowInstance).options(
                selectinload(WorkflowInstance.workflow_template)
            ).order_by(WorkflowInstance.created_at.desc()).limit(10)
            
            instances_result = await session.execute(instances_query)
            instances = instances_result.scalars().all()
            running_instances = [inst for inst in instances if inst.status in ["pending", "running"]]
            
            # ✅ FIX: Access all lazy-loaded attributes while session is active
            template_data = []
            for template in templates[:5]:
                template_data.append({
                    "id": str(template.id),
                    "name": template.name,
                    "active": template.is_active,
                    "nodes": len(template.nodes)  # ← Access nodes while session is active
                })
        
        return {
            "integration_status": "fully_connected",
            "evolution": {
                "phase_1": "Static workflows (direct service calls)",
                "phase_2": "Dynamic workflows (template-based DAG)",
                "current_phase": "Dynamic with full integration"
            },
            "existing_services": {
                "gmail_service": {
                    "status": "integrated",
                    "total_nodes": len(gmail_nodes),
                    "active_nodes": len(active_gmail_nodes),
                    "integration_method": "Service layer reuse",
                    "nodes": [
                        {
                            "id": str(node.id),
                            "email": node.email_address,
                            "active": node.is_active,
                            "emails_processed": node.emails_processed,
                            "can_use_in_dynamic_workflows": True
                        }
                        for node in gmail_nodes
                    ]
                },
                "classifier_service": {
                    "status": "integrated",
                    "description": "Connected to existing LLM client and classifier",
                    "integration_method": "Service layer reuse",
                    "provider": "Azure OpenAI"
                }
            },
            "dynamic_workflows": {
                "status": "operational",
                "total_templates": len(templates),
                "total_instances": len(instances),
                "running_instances": len(running_instances),
                "execution_engine": "DAG-based with topological sorting",
                "features": [
                    "Visual workflow builder support",
                    "Real-time execution monitoring", 
                    "Automatic data mapping",
                    "Error handling and retries",
                    "Service integration"
                ],
                "templates": template_data
            },
            "capabilities": {
                "can_create_workflows": len(gmail_nodes) > 0,
                "can_reuse_existing_nodes": True,
                "supports_drag_drop_ui": True,
                "supports_real_time_monitoring": True,
                "supports_complex_data_mapping": True
            },
            "next_steps": [
                "Add more node types (ServiceNow, Jira, etc.)",
                "Build visual workflow builder UI",
                "Add workflow scheduling",
                "Add advanced error handling"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))