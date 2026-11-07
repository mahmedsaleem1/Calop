import base64
import re

import httpx

from app.analysis.base import AnalysisError, AnalysisResult, FoodAnalyzer
from app.config import Settings

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

PROMPT = """You are a food nutrition expert. Look at this food image carefully.

Respond in this EXACT format (no extra text, no N/A, use 0 for unknown numbers):
FOOD: <food name>
CONFIDENCE: <decimal between 0.0 and 1.0>
CALORIES: <number only>
PROTEIN: <number only>g
CARBS: <number only>g
FAT: <number only>g
NOTES: <one short line>

The food is placed on a scale weighing {weight_g}g. Use that weight for nutrition calculation.
If you cannot identify food, use FOOD: unknown and CONFIDENCE: 0.0 and 0 for all numbers."""

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _number(value: str) -> float | None:
    m = _NUMBER.search(value)
    return float(m.group()) if m else None


class MistralAnalyzer(FoodAnalyzer):
    name = "mistral"

    def __init__(self, settings: Settings):
        self._key = settings.mistral_api_key
        self._model = settings.mistral_model

    def analyze(self, image: bytes, weight_g: float) -> AnalysisResult:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT.format(weight_g=round(weight_g, 1))},
                        {
                            "type": "image_url",
                            "image_url": "data:image/jpeg;base64," + base64.b64encode(image).decode(),
                        },
                    ],
                }
            ],
            "max_tokens": 200,
        }
        try:
            r = httpx.post(
                MISTRAL_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=30,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as e:
            raise AnalysisError(f"Mistral returned HTTP {e.response.status_code}") from e
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise AnalysisError(f"Mistral request failed: {type(e).__name__}") from e
        return self.parse(text)

    @staticmethod
    def parse(text: str) -> AnalysisResult:
        fields: dict[str, str] = {}
        for line in text.splitlines():
            key, sep, val = line.partition(":")
            if sep:
                fields[key.strip().upper()] = val.strip()
        confidence = _number(fields.get("CONFIDENCE", "")) or 0.0
        return AnalysisResult(
            label=fields.get("FOOD") or "unknown",
            confidence=min(max(confidence, 0.0), 1.0),
            calories=_number(fields.get("CALORIES", "")),
            protein_g=_number(fields.get("PROTEIN", "")),
            carbs_g=_number(fields.get("CARBS", "")),
            fat_g=_number(fields.get("FAT", "")),
            notes=fields.get("NOTES", ""),
        )
