from abc import ABC, abstractmethod


class ImageRateLimitError(Exception):
    """Erro de rate limit (HTTP 429) do motor de imagem — sinaliza ao Celery
    para usar um backoff mais longo (usado hoje só pelo Gemini)."""


class ImageEngineUnavailableError(Exception):
    """Erro de infraestrutura (timeout, HTTP 5xx ou 429) do motor de imagem
    atualmente ativo. Só é levantado pelo OpenAIImageEngine — sinaliza ao
    pipeline que a troca de motor deve ser oferecida ao usuário (RF4/RF5)."""


# Sufixo adicionado ao prompt positivo em todos os motores — reforça as regras
# de fundo branco/produto isolado que os prompts de texto nem sempre respeitam.
PROMPT_SUFFIX = (
    " Strict requirements: pure white (#FFFFFF) background only, product isolated and centered, "
    "no people, no hands, no text, no watermarks, no banners, no plants, no leaves, "
    "no furniture, no rooms, no shadows, no lifestyle elements, no extra products."
)


class ImageEngineProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> list[bytes]:
        """Gera imagens a partir do prompt. Retorna lista de bytes (JPEG/PNG)."""
