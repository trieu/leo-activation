


from agentic_models.function_gemma import FunctionGemmaEngine
from agentic_models.gemini import GeminiEngine


class LLMRouter:
    """
    Strategy:
    - tool-heavy / structured → FunctionGemma
    - semantic / reasoning → Gemini
    """

    def __init__(self, mode: str = "auto"):
        self.mode = mode
        self.gemma = FunctionGemmaEngine()
        self.gemini = GeminiEngine()

    def generate(self, messages, tools=None):
    
        if self.mode == "gemma":
            return self.gemma.generate(messages, tools)
        
        if self.mode == "gemini":
            return self.gemini.generate(messages, tools)

        # AUTO MODE
        if tools:
            return self.gemma.generate(messages, tools)

        # default to higher intelligence
        return self.gemini.generate(messages, tools)
