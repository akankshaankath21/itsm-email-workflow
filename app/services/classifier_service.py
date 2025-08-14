from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert
from app.llm_client import LLMClient
from app.nodes.mail_classifier import MailClassifierNode
from app.schemas import EnvelopeIn, ClassificationOut
from app.models import EmailRecord

class ClassifierService:
    """Service that runs the node and persists only label, priority, summary."""
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.classifier_node_id = "mail_classifier_node"

    async def classify_from_envelope(self, envelope: EnvelopeIn, session: AsyncSession) -> ClassificationOut:
        node = MailClassifierNode(id=self.classifier_node_id, name="Mail Classifier", type="action", llm=self.llm)
        node.inputData = envelope.model_dump()
        result = await node.execute()
        stmt = insert(EmailRecord).values(
            label=result["label"],
            priority=result["priority"],
            summary=result["summary"],
            subject=envelope.data.subject,
            body=envelope.data.body
        )
        await session.execute(stmt)
        await session.commit()
        return ClassificationOut(**result)