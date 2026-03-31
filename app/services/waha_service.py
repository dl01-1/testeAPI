# app/services/waha_service.py

import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# Cliente HTTP reutilizado entre requisições (performance)
_client = httpx.AsyncClient(timeout=30.0)


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key
    return headers


def _log_waha_error(label: str, response: httpx.Response) -> None:
    """Loga o status E o corpo da resposta de erro do WAHA — essencial para debug de 422."""
    try:
        body = response.json()
    except Exception:
        body = response.text
    logger.error(
        f"[WAHA] {label} falhou | "
        f"status={response.status_code} | "
        f"url={response.url} | "
        f"resposta_waha={body}"
    )


async def send_text(phone: str, text: str) -> None:
    """
    Envia mensagem de texto via WAHA.
    Loga o payload exato enviado para facilitar debug de 422.
    """
    url = f"{settings.waha_base_url}/api/sendText"
    payload = {
        "session": settings.waha_session,
        "chatId": phone,
        "text": text,
    }
    logger.info(f"[WAHA] send_text → url={url} | payload={payload}")

    response = await _client.post(url, json=payload, headers=_headers())

    if not response.is_success:
        _log_waha_error("send_text", response)
        response.raise_for_status()

    logger.info(f"[WAHA] send_text OK | status={response.status_code}")


async def send_typing(phone: str) -> None:
    """
    Simula 'digitando...' no WhatsApp.
    Falhas são ignoradas — typing é cosmético.
    """
    url = f"{settings.waha_base_url}/api/startTyping"
    payload = {
        "session": settings.waha_session,
        "chatId": phone,
    }
    logger.info(f"[WAHA] send_typing → url={url} | chatId={phone}")
    try:
        response = await _client.post(url, json=payload, headers=_headers())
        if not response.is_success:
            _log_waha_error("send_typing (non-fatal)", response)
        else:
            logger.info(f"[WAHA] send_typing OK")
    except Exception as e:
        logger.warning(f"[WAHA] send_typing falhou (ignorado): {e}")


async def download_media(phone: str, message_id: str) -> bytes:
    """
    Baixa mídia (áudio OGG) de uma mensagem do WAHA.
    """
    url = f"{settings.waha_base_url}/api/downloadMedia"
    payload = {
        "session": settings.waha_session,
        "messageId": message_id,
    }
    logger.info(f"[WAHA] download_media → message_id={message_id}")
    response = await _client.post(url, json=payload, headers=_headers())

    if not response.is_success:
        _log_waha_error("download_media", response)
        response.raise_for_status()

    logger.info(f"[WAHA] download_media OK | {len(response.content)} bytes")
    return response.content
