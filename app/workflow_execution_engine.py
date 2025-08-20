import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.workflow_models import (
    WorkflowTemplate, WorkflowNode, WorkflowEdge, WorkflowInstance, NodeExecution
)

from app.services.gmail_service import GmailService
from app.services.classifier_service import ClassifierService
from app.models import GmailNode, EmailRecord
from app.schemas import EnvelopeIn, EnvelopeData

class WorkflowExecutionEngine:
    
    def __init__(self):
        # Use your existing services instead of creating new nodes
        self.gmail_service = GmailService()
        self.classifier_service = ClassifierService()
        self.running_workflows: Dict[UUID, asyncio.Task] = {}
    
    async def execute_workflow(
        self, 
        template_id: UUID, 
        session: AsyncSession,
        trigger_data: Optional[Dict[str, Any]] = None,
        triggered_by: str = "manual"
    ) -> UUID:
        """Execute a workflow template and return the instance ID"""
        
        # Load workflow template
        workflow_template = await self._load_workflow_template(template_id, session)
        if not workflow_template:
            raise ValueError(f"Workflow template {template_id} not found")
        
        if not workflow_template.is_active:
            raise ValueError(f"Workflow template '{workflow_template.name}' is not active")
        
        # Create workflow instance
        workflow_instance = WorkflowInstance(
            id=uuid4(),
            workflow_template_id=template_id,
            status="pending",
            input_data=trigger_data,
            triggered_by=triggered_by
        )
        
        session.add(workflow_instance)
        await session.commit()
        await session.refresh(workflow_instance)
        
        # Start async execution
        task = asyncio.create_task(
            self._execute_workflow_async(workflow_instance.id, session)
        )
        self.running_workflows[workflow_instance.id] = task
        
        return workflow_instance.id
    
    async def _execute_workflow_async(self, instance_id: UUID, session: AsyncSession) -> None:
        """Async execution of a workflow instance"""
        try:
            # Mark as running
            await self._update_workflow_status(instance_id, "running", session)
            
            # Load workflow instance with template
            workflow_instance = await self._load_workflow_instance(instance_id, session)
            if not workflow_instance:
                raise ValueError(f"Workflow instance {instance_id} not found")
            
            template = workflow_instance.workflow_template
            
            # Build execution graph
            execution_graph = self._build_execution_graph(template)
            
            # Execute nodes in order
            await self._execute_nodes_in_order(workflow_instance, execution_graph, session)
            
            # Mark as completed
            await self._update_workflow_status(instance_id, "completed", session)
            
        except Exception as e:
            await self._update_workflow_status(instance_id, "failed", session, error_message=str(e))
            raise
        finally:
            if instance_id in self.running_workflows:
                del self.running_workflows[instance_id]
    
    def _build_execution_graph(self, template: WorkflowTemplate) -> Dict[str, Any]:
        """Build execution graph from workflow template"""
        nodes_map = {node.node_key: node for node in template.nodes}
        edges_map = {}
        
        # Build dependencies
        dependencies = {node.node_key: [] for node in template.nodes}
        
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
                dependencies[target_key].append(source_key)
                edges_map[(source_key, target_key)] = edge
        
        # Calculate execution order
        execution_order = self._topological_sort(dependencies)
        
        return {
            "nodes": nodes_map,
            "edges": edges_map,
            "execution_order": execution_order
        }
    
    def _topological_sort(self, dependencies: Dict[str, List[str]]) -> List[str]:
        """Topological sort to determine node execution order"""
        in_degree = {node: len(deps) for node, deps in dependencies.items()}
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            for node, deps in dependencies.items():
                if current in deps:
                    in_degree[node] -= 1
                    if in_degree[node] == 0:
                        queue.append(node)
        
        if len(result) != len(dependencies):
            raise ValueError("Workflow contains cycles - not a valid DAG")
        
        return result
    
    async def _execute_nodes_in_order(
        self,
        workflow_instance: WorkflowInstance,
        execution_graph: Dict[str, Any],
        session: AsyncSession
    ) -> None:
        """Execute nodes using existing services"""
        
        nodes_map = execution_graph["nodes"]
        edges_map = execution_graph["edges"]
        execution_order = execution_graph["execution_order"]
        
        completed_nodes: Dict[str, Dict[str, Any]] = {}
        execution_order_counter = 0
        
        for node_key in execution_order:
            execution_order_counter += 1
            workflow_node = nodes_map[node_key]
            
            if not workflow_node.is_enabled:
                continue
            
            try:
                # Create node execution record
                node_execution = NodeExecution(
                    id=uuid4(),
                    workflow_instance_id=workflow_instance.id,
                    workflow_node_id=workflow_node.id,
                    execution_order=execution_order_counter,
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                session.add(node_execution)
                await session.commit()
                await session.refresh(node_execution)
                
                # Prepare input data
                input_data = await self._prepare_node_input(
                    node_key, completed_nodes, edges_map
                )
                
                # Execute using existing services
                output_data = await self._execute_existing_service(workflow_node, input_data, session)
                
                # Mark as completed
                completed_at = datetime.now(timezone.utc)
                duration_ms = int((completed_at - node_execution.started_at).total_seconds() * 1000)
                
                await session.execute(
                    update(NodeExecution)
                    .where(NodeExecution.id == node_execution.id)
                    .values(
                        status="completed",
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        input_data=input_data,
                        output_data=output_data
                    )
                )
                
                # Store output for downstream nodes
                completed_nodes[node_key] = output_data
                await session.commit()
                
            except Exception as e:
                # Mark as failed
                await session.execute(
                    update(NodeExecution)
                    .where(NodeExecution.id == node_execution.id)
                    .values(
                        status="failed",
                        completed_at=datetime.now(timezone.utc),
                        error_message=str(e)
                    )
                )
                await session.commit()
                raise RuntimeError(f"Node '{node_key}' failed: {str(e)}")
    
    async def _execute_existing_service(
        self,
        workflow_node: WorkflowNode,
        input_data: Dict[str, Any],
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Execute using your existing services instead of creating new nodes"""
        
        node_class = workflow_node.node_class
        config = workflow_node.configuration
        
        if node_class == "GmailTriggerNode":
            # Use your existing Gmail service
            # Find the Gmail node that matches this configuration
            gmail_nodes = await self.gmail_service.list_gmail_nodes(session)
            
            # Find matching Gmail node by email address
            matching_node = None
            target_email = config.get("email_address")
            
            for gmail_node in gmail_nodes:
                if gmail_node.email_address == target_email:
                    matching_node = gmail_node
                    break
            
            if not matching_node:
                # Create a temporary Gmail node for this execution
                from app.schemas import GmailNodeConfigIn
                gmail_config = GmailNodeConfigIn(
                    name=workflow_node.name,
                    email_address=config["email_address"],
                    credentials_file_path=config["credentials_file_path"],
                    token_file_path=config.get("token_file_path", "gmail_token.json"),
                    polling_interval=config.get("polling_interval", 30),
                    max_results=config.get("max_results", 10)
                )
                matching_node = await self.gmail_service.create_gmail_node(gmail_config, session)
            
            # Get emails from your existing Gmail service
            emails = await self.gmail_service.get_raw_emails(matching_node.id, session, limit=config.get("max_results", 10))
            
            # Transform to expected format
            email_data = []
            for email in emails:
                email_data.append({
                    "id": str(email.id),
                    "from": email.from_address,
                    "to": email.to_address,
                    "subject": email.subject,
                    "body": email.body,
                    "received_at": email.received_at.isoformat()
                })
            
            return {
                "emails": email_data,
                "emails_count": len(email_data)
            }
            
        elif node_class == "MailClassifierNode":
            # Use your existing classifier service
            if "input_emails" not in input_data:
                raise RuntimeError("MailClassifierNode requires 'input_emails' input")
            
            emails = input_data["input_emails"]
            classifications = []
            
            for email in emails:
                # Create envelope for your existing classifier
                envelope_data = EnvelopeData(
                    subject=email.get("subject"),
                    body=email.get("body", "")
                )
                envelope = EnvelopeIn(data=envelope_data)
                
                # Use your existing classifier service
                classification = await self.classifier_service.classify_from_envelope(envelope, session)
                
                classifications.append({
                    "email_id": email.get("id"),
                    "priority": classification.priority,
                    "label": classification.label,
                    "summary": classification.summary
                })
            
            return {
                "classifications": classifications
            }
        
        else:
            raise ValueError(f"Unknown node type: {node_class}")
    
    async def _prepare_node_input(
        self,
        target_node_key: str,
        completed_nodes: Dict[str, Dict[str, Any]],
        edges_map: Dict[Tuple[str, str], WorkflowEdge]
    ) -> Dict[str, Any]:
        """Prepare input data for a node using data mappings"""
        input_data = {}
        
        for (source_key, target_key), edge in edges_map.items():
            if target_key != target_node_key:
                continue
            
            if source_key not in completed_nodes:
                raise RuntimeError(f"Dependency '{source_key}' not completed for node '{target_node_key}'")
            
            source_output = completed_nodes[source_key]
            
            # Apply data mapping
            if edge.data_mapping:
                for source_field, target_field in edge.data_mapping.items():
                    if source_field in source_output:
                        input_data[target_field] = source_output[source_field]
            else:
                # No mapping - pass through all data
                input_data.update(source_output)
        
        return input_data
    
    async def _load_workflow_template(self, template_id: UUID, session: AsyncSession) -> Optional[WorkflowTemplate]:
        """Load workflow template with all nodes and edges"""
        result = await session.execute(
            select(WorkflowTemplate)
            .options(
                selectinload(WorkflowTemplate.nodes),
                selectinload(WorkflowTemplate.edges)
            )
            .where(WorkflowTemplate.id == template_id)
        )
        return result.scalar_one_or_none()
    
    async def _load_workflow_instance(self, instance_id: UUID, session: AsyncSession) -> Optional[WorkflowInstance]:
        """Load workflow instance with template"""
        result = await session.execute(
            select(WorkflowInstance)
            .options(
                selectinload(WorkflowInstance.workflow_template).selectinload(WorkflowTemplate.nodes),
                selectinload(WorkflowInstance.workflow_template).selectinload(WorkflowTemplate.edges)
            )
            .where(WorkflowInstance.id == instance_id)
        )
        return result.scalar_one_or_none()
    
    async def _update_workflow_status(
        self,
        instance_id: UUID,
        status: str,
        session: AsyncSession,
        error_message: Optional[str] = None
    ) -> None:
        """Update workflow instance status"""
        update_data = {"status": status, "updated_at": datetime.now(timezone.utc)}
        
        if status == "running":
            update_data["started_at"] = datetime.now(timezone.utc)
        elif status in ["completed", "failed"]:
            update_data["completed_at"] = datetime.now(timezone.utc)
        
        if error_message:
            update_data["error_message"] = error_message
        
        await session.execute(
            update(WorkflowInstance)
            .where(WorkflowInstance.id == instance_id)
            .values(**update_data)
        )
        await session.commit()
    
    async def get_workflow_status(self, instance_id: UUID, session: AsyncSession) -> Optional[Dict[str, Any]]:
        """Get detailed workflow execution status"""
        result = await session.execute(
            select(WorkflowInstance)
            .options(
                selectinload(WorkflowInstance.node_executions).selectinload(NodeExecution.workflow_node)
            )
            .where(WorkflowInstance.id == instance_id)
        )
        workflow_instance = result.scalar_one_or_none()
        
        if not workflow_instance:
            return None
        
        node_statuses = []
        for execution in workflow_instance.node_executions:
            node_statuses.append({
                "node_key": execution.workflow_node.node_key,
                "node_name": execution.workflow_node.name,
                "status": execution.status,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "duration_ms": execution.duration_ms,
                "error_message": execution.error_message
            })
        
        return {
            "instance_id": str(workflow_instance.id),
            "template_name": workflow_instance.workflow_template.name,
            "status": workflow_instance.status,
            "started_at": workflow_instance.started_at.isoformat() if workflow_instance.started_at else None,
            "completed_at": workflow_instance.completed_at.isoformat() if workflow_instance.completed_at else None,
            "error_message": workflow_instance.error_message,
            "nodes": node_statuses,
            "is_running": instance_id in self.running_workflows
        }

# Global execution engine instance
workflow_engine = WorkflowExecutionEngine()