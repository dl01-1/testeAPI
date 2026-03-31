# app/models/waha_models.py

from pydantic import BaseModel, Field
from typing import Optional


# --- Modelos aninhados (seguem a estrutura exata do payload do WAHA) ---

class MessageId(BaseModel):
    """Identifica se a mensagem foi enviada pelo próprio bot."""
    fromMe: bool = False
    id: Optional[str] = None

    model_config = {"extra": "ignore"}  # ignora campos desconhecidos do WAHA


class MessageData(BaseModel):
    """
    Dados extras da mensagem.
    No JSON do WAHA este campo chama-se literalmente "_data".
    BUG CORRIGIDO: '_data: Optional[...]' era atributo privado do Pydantic e
    nunca recebia valor. A solução é declarar com alias="_data".
    """
    notifyName: Optional[str] = None
    id: Optional[MessageId] = None

    model_config = {"extra": "ignore"}


class Payload(BaseModel):
    """
    O coração do webhook.
    BUG CORRIGIDO: 'data_' usa Field(alias="_data") para mapear o campo JSON
    "_data" sem conflito com atributos privados do Pydantic.
    """
    id: Optional[str] = None
    from_: str = Field(alias="from")        # "from" é palavra reservada em Python
    to: Optional[str] = None
    body: Optional[str] = None             # texto da mensagem
    hasMedia: bool = False                 # True se for áudio/imagem
    source: Optional[str] = None          # "android", "web", "api" etc.
    data_: Optional[MessageData] = Field(  # ← alias correto para o campo "_data"
        default=None, alias="_data"
    )

    model_config = {
        "populate_by_name": True,  # aceita tanto o alias quanto o nome Python
        "extra": "ignore",         # campos desconhecidos do WAHA não causam erro
    }


class WAHAWebhook(BaseModel):
    """
    Modelo raiz do webhook do WAHA.
    BUG CORRIGIDO: instanciar com WAHAWebhook(**body) passa 'from' como kwarg
    Python (palavra reservada → TypeError). Usar sempre model_validate(body).
    """
    event: str        # ex: "message", "message.ack", "message.revoked"
    session: str
    payload: Payload

    model_config = {"extra": "ignore"}


# --- Modelo de resposta interna ---

class ParsedMessage(BaseModel):
    phone: str
    name: str
    text: str
    is_audio: bool = False
