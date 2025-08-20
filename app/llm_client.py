import json
from typing import Any, Literal, Tuple, Optional
import anyio
from openai import AzureOpenAI
from pydantic import BaseModel, Field, ValidationError
from app.config import settings

class LLMClassification(BaseModel):
    priority: Literal["P1", "P2", "P3"]
    label: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)

class LLMClient:
    def __init__(self) -> None:
        self.system_prompt = settings.llm_system_prompt
        self._deployment = settings.azure_openai_deployment
        self._azure_client: Optional[AzureOpenAI] = None
        self._azure_ready: bool = (
            not settings.llm_use_stub
            and bool(settings.azure_openai_api_key)
            and bool(settings.azure_openai_endpoint)
        )

    def _json_schema(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "email_classification",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string", "minLength": 1, "maxLength": 128},
                        "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
                        "summary": {"type": "string", "minLength": 1, "MaxLength": 2000, "maxLength": 2000},
                    },
                    "required": ["label", "priority", "summary"],
                },
                "strict": True,
            },
        }

    def _ensure_azure_client(self) -> None:
        if self._azure_client is None and self._azure_ready:
            self._azure_client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
            )

    async def classify_email(self, subject: Optional[str], body: str) -> Tuple[LLMClassification, dict]:
        subj = subject or ""
        if self._azure_ready:
            try:
                self._ensure_azure_client()
                schema = self._json_schema()

                def _call() -> dict:
                    return self._azure_client.chat.completions.create(
                        model=self._deployment,
                        temperature=0,
                        response_format=schema,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": json.dumps({"subject": subj, "body": body}, ensure_ascii=False)},
                        ],
                    ).model_dump()

                resp = await anyio.to_thread.run_sync(_call)
                content = resp["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                cls = LLMClassification(**parsed)
                meta = {"id": resp.get("id"), "model": resp.get("model"), "usage": resp.get("usage"), "content": parsed}
                return cls, meta
            except Exception:
                pass

        cls = self._stub_classify(subj, body)
        return cls, {"provider": "stub"}

    def _stub_classify(self, subject: str, body: str) -> LLMClassification:
        text = f"{subject}\n{body}".lower()
        p1_terms = ("outage", "down", "doesn't start", "won't start", "cannot start", "error code", "security", "breach", "payment failed", "urgent")
        p2_terms = ("bug", "crash", "blue screen", "issue", "not working", "delay")
        pr = "P3"
        if any(t in text for t in p1_terms):
            pr = "P1"
        elif any(t in text for t in p2_terms):
            pr = "P2"
        lbl = "System Outage" if pr == "P1" else ("Product Issue" if pr == "P2" else "General Query")
        summary = "High-impact failure requiring immediate attention." if pr == "P1" else ("Customer-reported defect impacting usability." if pr == "P2" else "Non-urgent inquiry or information request.")
        try:
            return LLMClassification(priority=pr, label=lbl, summary=summary)
        except ValidationError:
            return LLMClassification(priority="P3", label="General Query", summary="Non-urgent inquiry or information request.")