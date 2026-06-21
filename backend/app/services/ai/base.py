from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    async def generate_titles(self, sku_description: str, sku_brand: str, condition: str) -> list[dict]:
        """Retorna lista de {text, score, rationale}"""

    @abstractmethod
    async def generate_description(self, listing_data: dict) -> str:
        """Retorna HTML string"""

    @abstractmethod
    async def generate_image_prompt(self, brand: str, title: str, description: str) -> str:
        """Retorna prompt em inglês otimizado para Imagen 4"""
