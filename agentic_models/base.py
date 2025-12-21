from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseLLMEngine(ABC):
    """
    Contract for all LLM backends.
    """

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]] | None = None
    ) -> str:
        pass

    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        Optional override.
        Default: no tool calls.
        """
        return []
