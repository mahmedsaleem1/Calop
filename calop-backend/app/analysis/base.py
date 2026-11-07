from abc import ABC, abstractmethod
from dataclasses import dataclass


class AnalysisError(Exception):
    pass


@dataclass
class AnalysisResult:
    label: str
    confidence: float
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    notes: str


class FoodAnalyzer(ABC):
    """Identifies food from an image and estimates nutrition for the measured weight.
    Mistral today; a self-hosted model or a lookup-table calculation can replace it later."""

    name: str

    @abstractmethod
    def analyze(self, image: bytes, weight_g: float) -> AnalysisResult: ...
