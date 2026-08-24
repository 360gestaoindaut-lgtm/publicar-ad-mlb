from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = ""

    # Redis
    redis_url: str = ""

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Fernet — criptografa tokens ML no banco
    fernet_key: str

    # Mercado Livre
    ml_app_id: str
    ml_client_secret: str
    ml_redirect_uri: str

    # IA
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # OpenAI (motor de imagem alternativo — gpt-image-2)
    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-2"

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "publicar-ad-mlb"
    r2_public_url: str = ""

    # App
    #
    # ATENCAO — este default e INSEGURO por design, e o risco so aparece por
    # omissao: `main.py` publica o Swagger (`/docs`) enquanto o valor for
    # "development". Como esse e justamente o default, QUALQUER ambiente que
    # esqueca de setar a variavel sobe com a documentacao inteira da API
    # aberta — inclusive uma VPS exposta a internet.
    #
    # Todo ambiente que nao for dev explicito precisa setar
    # ENVIRONMENT=production. O `docker-compose.prod.yml` ja crava o valor na
    # secao `environment:` do backend, worker e beat, justamente para nao
    # depender do .env daquele servidor estar completo.
    environment: str = "development"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
