from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RecognizedCandidate:
    code: str
    confidence: float


@dataclass
class RecognitionOutput:
    candidates: list[RecognizedCandidate]
    not_in_catalog_label: str | None
    raw_response: dict
    input_tokens: int | None
    output_tokens: int | None


class RecognizerRateLimited(Exception):
    pass


class RecognizerError(Exception):
    pass


class FoodRecognizer(ABC):
    """Identifies the food in a photo. Business code depends on this interface only, never on a provider SDK."""

    @abstractmethod
    def recognize(self, image_jpeg: bytes, catalog_text: str, system_prompt: str) -> RecognitionOutput: ...
