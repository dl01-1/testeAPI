# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centraliza TODAS as configurações da aplicação.

    Pydantic Settings lê automaticamente do arquivo .env e valida os tipos.
    Se uma variável obrigatória (sem default) estiver faltando, a aplicação
    para na inicialização com um erro claro — muito melhor do que um
    KeyError silencioso em produção às 3 da manhã.
    """

    # --- Groq ---
    groq_api_key: str  # obrigatório: sem default → erro claro se faltar

    # --- WAHA ---
    waha_base_url: str = ""
    waha_session: str = "default"
    waha_api_key: str = ""

    # --- Comportamento do bot ---
    memory_max_turns: int = 10  # quantas trocas de mensagem o bot "lembra"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# Instância única (padrão Singleton).
# Em todo o projeto: from app.core.config import settings
settings = Settings()
