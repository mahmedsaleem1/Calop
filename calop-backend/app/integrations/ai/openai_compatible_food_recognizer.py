"""The only file that imports `openai`. Works with any OpenAI-compatible vision API (Gemini by default)."""
import base64

import openai
import pydantic
from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.integrations.ai.food_recognizer import (
    FoodRecognizer, RecognitionOutput, RecognizedCandidate, RecognizerError, RecognizerRateLimited,
)


class _Candidate(BaseModel):
    code: str
    confidence: float = Field(ge=0, le=1)


class _Result(BaseModel):
    candidates: list[_Candidate] = Field(max_length=3)
    not_in_catalog_label: str | None


class OpenAICompatibleFoodRecognizer(FoodRecognizer):
    def __init__(self, settings: Settings):
        self._model = settings.vision_ai_model
        self._reasoning_effort = settings.vision_ai_reasoning_effort
        # Retries are handled by the job queue, so the SDK must not retry on its own.
        self._client = OpenAI(
            base_url=settings.vision_ai_base_url,
            api_key=settings.vision_ai_api_key,
            timeout=settings.vision_ai_timeout_seconds,
            max_retries=0,
        )

    def recognize(self, image_jpeg: bytes, catalog_text: str, system_prompt: str) -> RecognitionOutput:
        encoded = base64.b64encode(image_jpeg).decode("ascii")
        request = dict(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Catalog:\n{catalog_text}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                    ],
                },
            ],
            response_format=_Result,
        )
        if self._reasoning_effort:
            request["reasoning_effort"] = self._reasoning_effort

        try:
            completion = self._client.chat.completions.parse(**request)
        except openai.RateLimitError as exc:
            raise RecognizerRateLimited(str(exc)) from exc
        except (openai.OpenAIError, pydantic.ValidationError, ValueError) as exc:
            raise RecognizerError(f"{type(exc).__name__}: {exc}") from exc

        message = completion.choices[0].message if completion.choices else None
        parsed = message.parsed if message is not None else None
        if parsed is None:
            refusal = getattr(message, "refusal", None) if message is not None else None
            raise RecognizerError(f"The model returned no valid result{': ' + refusal if refusal else ''}")

        usage = completion.usage
        return RecognitionOutput(
            candidates=[RecognizedCandidate(code=c.code.strip(), confidence=c.confidence) for c in parsed.candidates],
            not_in_catalog_label=parsed.not_in_catalog_label,
            raw_response=completion.model_dump(mode="json"),
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
