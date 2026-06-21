from app.config import get_settings
from app.services.ai.base import AIProvider


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "claude":
        from app.services.ai.claude import ClaudeProvider
        return ClaudeProvider()
    from app.services.ai.gemini import GeminiProvider
    return GeminiProvider()
