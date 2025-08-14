from typing import Any
from app.nodes.base import BaseNode
from app.llm_client import LLMClient
from app.schemas import EnvelopeIn, ClassificationOut

class MailClassifierNode(BaseNode):
    """Node that extracts subject/body from an envelope and classifies via LLM."""
    def __init__(self, id: str, name: str, type: str, llm: LLMClient) -> None:
        super().__init__(id=id, name=name, type=type)
        self.llm = llm
        self.meta: dict | None = None

    async def execute(self) -> Any:
        if not self.inputData:
            raise ValueError("No inputData provided to MailClassifierNode")
        envelope = EnvelopeIn.model_validate(self.inputData)
        self.isActive = True
        classification, meta = await self.llm.classify_email(envelope.data.subject, envelope.data.body)
        self.meta = meta
        out = ClassificationOut(priority=classification.priority, label=classification.label, summary=classification.summary)
        self.setOutput(out.model_dump())
        self.isActive = False
        return self.getOutput()