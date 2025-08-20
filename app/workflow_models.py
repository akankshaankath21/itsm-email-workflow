import uuid
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any, List
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Enum, Text, DateTime, Index, Boolean, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db import Base

class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    
    # Workflow metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Execution settings
    max_concurrent_instances: Mapped[int] = mapped_column(Integer, default=5)
    timeout_minutes: Mapped[int] = mapped_column(Integer, default=30)
    
    # UI Layout information
    ui_layout: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Audit fields
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


    nodes: Mapped[List["WorkflowNode"]] = relationship("WorkflowNode", back_populates="workflow_template", cascade="all, delete-orphan")
    edges: Mapped[List["WorkflowEdge"]] = relationship("WorkflowEdge", back_populates="workflow_template", cascade="all, delete-orphan")
    instances: Mapped[List["WorkflowInstance"]] = relationship("WorkflowInstance", back_populates="workflow_template")

    __table_args__ = (
        Index("ix_workflow_templates_name", "name"),
        Index("ix_workflow_templates_is_active", "is_active"),
    )

class WorkflowNode(Base):
    """Individual nodes within a workflow template"""
    __tablename__ = "workflow_nodes"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_templates.id"), nullable=False)
    
    # Node identification
    node_key: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[Literal["trigger", "action"]] = mapped_column(Enum("trigger", "action", name="node_type_enum"), nullable=False)
    node_class: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Node metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Node configuration
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    
    # UI positioning
    ui_position: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Execution settings
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    

    workflow_template: Mapped["WorkflowTemplate"] = relationship("WorkflowTemplate", back_populates="nodes")
    outgoing_edges: Mapped[List["WorkflowEdge"]] = relationship("WorkflowEdge", foreign_keys="WorkflowEdge.source_node_id", back_populates="source_node")
    incoming_edges: Mapped[List["WorkflowEdge"]] = relationship("WorkflowEdge", foreign_keys="WorkflowEdge.target_node_id", back_populates="target_node")
    executions: Mapped[List["NodeExecution"]] = relationship("NodeExecution", back_populates="workflow_node")

    __table_args__ = (
        UniqueConstraint("workflow_template_id", "node_key", name="uq_workflow_node_key"),
        Index("ix_workflow_nodes_template_id", "workflow_template_id"),
    )

class WorkflowEdge(Base):
    """Connections between workflow nodes"""
    __tablename__ = "workflow_edges"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_templates.id"), nullable=False)
    
    # Edge definition
    source_node_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_nodes.id"), nullable=False)
    target_node_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_nodes.id"), nullable=False)
    
    # Data mapping configuration
    data_mapping: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Edge settings
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    

    workflow_template: Mapped["WorkflowTemplate"] = relationship("WorkflowTemplate", back_populates="edges")
    source_node: Mapped["WorkflowNode"] = relationship("WorkflowNode", foreign_keys=[source_node_id], back_populates="outgoing_edges")
    target_node: Mapped["WorkflowNode"] = relationship("WorkflowNode", foreign_keys=[target_node_id], back_populates="incoming_edges")

    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", name="uq_workflow_edge"),
        Index("ix_workflow_edges_template_id", "workflow_template_id"),
    )

class WorkflowInstance(Base):
    """A specific execution instance of a workflow template"""
    __tablename__ = "workflow_instances"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_templates.id"), nullable=False)
    
    # Execution state
    status: Mapped[Literal["pending", "running", "completed", "failed", "cancelled"]] = mapped_column(
        Enum("pending", "running", "completed", "failed", "cancelled", name="workflow_status_enum"), 
        nullable=False, default="pending"
    )
    
    # Execution details
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Input/Output data
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Triggered by
    triggered_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


    workflow_template: Mapped["WorkflowTemplate"] = relationship("WorkflowTemplate", back_populates="instances")
    node_executions: Mapped[List["NodeExecution"]] = relationship("NodeExecution", back_populates="workflow_instance", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workflow_instances_template_id", "workflow_template_id"),
        Index("ix_workflow_instances_status", "status"),
    )

class NodeExecution(Base):
    """Track individual node executions within a workflow instance"""
    __tablename__ = "node_executions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_instances.id"), nullable=False)
    workflow_node_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflow_nodes.id"), nullable=False)
    
    # Execution details
    execution_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[Literal["pending", "running", "completed", "failed", "skipped"]] = mapped_column(
        Enum("pending", "running", "completed", "failed", "skipped", name="node_execution_status_enum"), 
        nullable=False, default="pending"
    )
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Input/Output
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


    workflow_instance: Mapped["WorkflowInstance"] = relationship("WorkflowInstance", back_populates="node_executions")
    workflow_node: Mapped["WorkflowNode"] = relationship("WorkflowNode", back_populates="executions")

    __table_args__ = (
        Index("ix_node_executions_instance_id", "workflow_instance_id"),
        Index("ix_node_executions_node_id", "workflow_node_id"),
    )