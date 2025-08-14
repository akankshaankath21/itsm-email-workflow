from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import EnvelopeIn, ExecuteResponse
from app.services.classifier_service import ClassifierService

class MailController:
    """Controller that handles Gmail envelope classification."""
    def __init__(self) -> None:
        self.service = ClassifierService()

    async def execute_from_envelope(self, payload: EnvelopeIn, session: AsyncSession) -> ExecuteResponse:
        record = await self.service.classify_from_envelope(payload, session)
        return ExecuteResponse(data=record)