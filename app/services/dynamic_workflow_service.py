from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.workflow_models import WorkflowTemplate, WorkflowNode, WorkflowEdge, WorkflowInstance
from app.workflow_execution_engine import workflow_engine

class DynamicWorkflowService:
    """Service layer for managing dynamic workflows"""
    
    async def create_workflow_template(
        self,
        name: str,
        description: Optional[str],
        session: AsyncSession,
        category: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> WorkflowTemplate:
        """Create a new workflow template"""
        template = WorkflowTemplate(
            id=uuid4(),
            name=name,
            description=description,
            category=category,
            created_by=created_by,
            is_active=True,
            ui_layout={}
        )
        
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template
    
    async def add_node_to_workflow(
        self,
        template_id: UUID,
        node_key: str,
        node_type: str,
        node_class: str,
        name: str,
        configuration: Dict[str, Any],
        session: AsyncSession,
        description: Optional[str] = None,
        ui_position: Optional[Dict[str, Any]] = None
    ) -> WorkflowNode:
        """Add a node to an existing workflow template"""
        
        # Verify template exists
        template = await session.get(WorkflowTemplate, template_id)
        if not template:
            raise ValueError(f"Workflow template {template_id} not found")
        
        # Check for duplicate node_key
        existing_node = await session.execute(
            select(WorkflowNode).where(
                WorkflowNode.workflow_template_id == template_id,
                WorkflowNode.node_key == node_key
            )
        )
        if existing_node.scalar_one_or_none():
            raise ValueError(f"Node with key '{node_key}' already exists in workflow")
        
        # Create the node
        workflow_node = WorkflowNode(
            id=uuid4(),
            workflow_template_id=template_id,
            node_key=node_key,
            node_type=node_type,
            node_class=node_class,
            name=name,
            description=description,
            configuration=configuration,
            ui_position=ui_position or {"x": 0, "y": 0},
            is_enabled=True
        )
        
        session.add(workflow_node)
        await session.commit()
        await session.refresh(workflow_node)
        return workflow_node
    
    async def add_edge_to_workflow(
        self,
        template_id: UUID,
        source_node_key: str,
        target_node_key: str,
        data_mapping: Dict[str, str],
        session: AsyncSession,
        name: Optional[str] = None
    ) -> WorkflowEdge:
        """Add an edge (connection) between two nodes in a workflow"""
        
        # Get source and target nodes
        source_node = await session.execute(
            select(WorkflowNode).where(
                WorkflowNode.workflow_template_id == template_id,
                WorkflowNode.node_key == source_node_key
            )
        )
        source_node = source_node.scalar_one_or_none()
        if not source_node:
            raise ValueError(f"Source node '{source_node_key}' not found")
        
        target_node = await session.execute(
            select(WorkflowNode).where(
                WorkflowNode.workflow_template_id == template_id,
                WorkflowNode.node_key == target_node_key
            )
        )
        target_node = target_node.scalar_one_or_none()
        if not target_node:
            raise ValueError(f"Target node '{target_node_key}' not found")
        
        # Check for duplicate edge
        existing_edge = await session.execute(
            select(WorkflowEdge).where(
                WorkflowEdge.source_node_id == source_node.id,
                WorkflowEdge.target_node_id == target_node.id
            )
        )
        if existing_edge.scalar_one_or_none():
            raise ValueError(f"Edge from '{source_node_key}' to '{target_node_key}' already exists")
        
        # Create the edge
        workflow_edge = WorkflowEdge(
            id=uuid4(),
            workflow_template_id=template_id,
            source_node_id=source_node.id,
            target_node_id=target_node.id,
            data_mapping=data_mapping,
            is_enabled=True
        )
        
        session.add(workflow_edge)
        await session.commit()
        await session.refresh(workflow_edge)
        return workflow_edge
    
    async def get_workflow_template(
        self,
        template_id: UUID,
        session: AsyncSession
    ) -> Optional[WorkflowTemplate]:
        """Get a workflow template with all nodes and edges"""
        result = await session.execute(
            select(WorkflowTemplate)
            .options(
                selectinload(WorkflowTemplate.nodes),
                selectinload(WorkflowTemplate.edges).selectinload(WorkflowEdge.source_node),
                selectinload(WorkflowTemplate.edges).selectinload(WorkflowEdge.target_node)
            )
            .where(WorkflowTemplate.id == template_id)
        )
        return result.scalar_one_or_none()
    
    async def list_workflow_templates(
        self,
        session: AsyncSession,
        active_only: bool = True,
        category: Optional[str] = None
    ) -> List[WorkflowTemplate]:
        """List workflow templates with optional filtering"""
        query = select(WorkflowTemplate)
        
        if active_only:
            query = query.where(WorkflowTemplate.is_active == True)
        
        if category:
            query = query.where(WorkflowTemplate.category == category)
        
        query = query.order_by(WorkflowTemplate.created_at.desc())
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def execute_workflow_template(
        self,
        template_id: UUID,
        session: AsyncSession,
        trigger_data: Optional[Dict[str, Any]] = None,
        triggered_by: str = "manual"
    ) -> UUID:
        """Execute a workflow template and return instance ID"""
        
        # Validate template exists and is active
        template = await self.get_workflow_template(template_id, session)
        if not template:
            raise ValueError(f"Workflow template {template_id} not found")
        
        if not template.is_active:
            raise ValueError(f"Workflow template '{template.name}' is not active")
        
        # Validate DAG structure
        await self._validate_workflow_dag(template)
        
        # Execute using the engine
        instance_id = await workflow_engine.execute_workflow(
            template_id, session, trigger_data, triggered_by
        )
        
        return instance_id
    
    async def _validate_workflow_dag(self, template: WorkflowTemplate) -> None:
        """Validate that the workflow forms a valid DAG"""
        
        # Check for at least one node
        if not template.nodes:
            raise ValueError("Workflow must have at least one node")
        
        # Check for trigger nodes
        trigger_nodes = [node for node in template.nodes if node.node_type == "trigger"]
        if not trigger_nodes:
            raise ValueError("Workflow must have at least one trigger node")
        
        # Build adjacency list to check for cycles
        adjacency = {node.node_key: [] for node in template.nodes}
        
        for edge in template.edges:
            if not edge.is_enabled:
                continue
                
            source_key = None
            target_key = None
            
            for node in template.nodes:
                if node.id == edge.source_node_id:
                    source_key = node.node_key
                elif node.id == edge.target_node_id:
                    target_key = node.node_key
            
            if source_key and target_key:
                adjacency[source_key].append(target_key)
        
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node_key in adjacency:
            if node_key not in visited:
                if has_cycle(node_key):
                    raise ValueError("Workflow contains cycles - not a valid DAG")
    
    async def get_workflow_instance_status(
        self,
        instance_id: UUID,
        session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Get detailed status of a workflow instance"""
        return await workflow_engine.get_workflow_status(instance_id, session)
    
    async def list_workflow_instances(
        self,
        session: AsyncSession,
        template_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[WorkflowInstance]:
        """List workflow instances with optional filtering"""
        query = select(WorkflowInstance).options(
            selectinload(WorkflowInstance.workflow_template)
        )
        
        if template_id:
            query = query.where(WorkflowInstance.workflow_template_id == template_id)
        
        if status:
            query = query.where(WorkflowInstance.status == status)
        
        query = query.order_by(WorkflowInstance.created_at.desc()).limit(limit)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def delete_workflow_template(
        self,
        template_id: UUID,
        session: AsyncSession
    ) -> bool:
        """Delete a workflow template"""
        
        # Check if template has running instances
        running_instances = await session.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.workflow_template_id == template_id,
                WorkflowInstance.status.in_(["pending", "running"])
            )
        )
        
        if running_instances.scalars().first():
            raise ValueError("Cannot delete template with running instances")
        
        # Delete template (cascade will handle nodes, edges, etc.)
        await session.execute(
            delete(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
        )
        await session.commit()
        return True

# Helper function to create a sample workflow template
async def create_sample_gmail_classifier_workflow(
    session: AsyncSession,
    service: DynamicWorkflowService,
    gmail_config: Dict[str, Any]
) -> UUID:
    """Create a sample Gmail → Classifier workflow template"""
    
    # Create template
    template = await service.create_workflow_template(
        name="Gmail to Email Classifier",
        description="Monitors Gmail for new emails and classifies them using AI",
        category="Email Processing",
        session=session
    )
    
    # Add Gmail trigger node
    await service.add_node_to_workflow(
        template_id=template.id,
        node_key="gmail_trigger",
        node_type="trigger",
        node_class="GmailTriggerNode",
        name="Gmail Monitor",
        configuration=gmail_config,
        ui_position={"x": 100, "y": 100},
        session=session
    )
    
    # Add classifier node
    await service.add_node_to_workflow(
        template_id=template.id,
        node_key="email_classifier",
        node_type="action", 
        node_class="MailClassifierNode",
        name="Email Classifier",
        configuration={"llm_model": "gpt-4"},
        ui_position={"x": 400, "y": 100},
        session=session
    )
    
    # Add edge connecting them
    await service.add_edge_to_workflow(
        template_id=template.id,
        source_node_key="gmail_trigger",
        target_node_key="email_classifier",
        data_mapping={"emails": "input_emails"},
        name="Email Flow",
        session=session
    )
    
    return template.id