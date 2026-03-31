# app/routers/webhook.py

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.models.waha_models import WAHAWebhook
from app.services import groq_service, waha_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["webhook"])

# ─────────────────────────────────────────────
# Eventos que o WAHA manda mas não são mensagens
# ─────────────────────────────────────────────
_IGNORED_EVENTS = {
    "message.ack", "message.revoked", "message.reaction",
    "session.status", "state.change", "group.join", "group.leave",
    "call", "presence.update",
}


def _should_ignore(webhook: WAHAWebhook) -> tuple[bool, str]:
    """Filtros equivalentes aos nós grupo1 / api1 / fromMe do n8n."""
    
    # 1. Filtra eventos de sistema pela sua lista
    if webhook.event in _IGNORED_EVENTS:
        return True, f"ignored_event_{webhook.event}"

    # 2. Garante que SÓ processamos eventos de mensagens reais
    if webhook.event not in ("message", "message.any"):
        return True, f"unhandled_event_{webhook.event}"

    payload = webhook.payload

    # Evento que não é mensagem recebida
    # Mensagem enviada pelo próprio bot → evita loop infinito
    if payload.data_ and payload.data_.id and payload.data_.id.fromMe:
        return True, "fromMe=true"

    # Mensagem de grupo (@g.us) → nó grupo1 do n8n
    if payload.to and "@g.us" in payload.to:
        return True, "group_message"

    # Mensagem enviada via API → nó api1 do n8n
    if payload.source == "api":
        return True, "source=api"

    # Sem conteúdo processável
    if not payload.body and not payload.hasMedia:
        return True, "empty_body_no_media"

    return False, ""


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,      # ← injeção do FastAPI (mais seguro que create_task)
) -> JSONResponse:
    """
    Recebe eventos do WAHA e responde 200 imediatamente.
    O processamento pesado (Groq, envio) roda em BackgroundTask.

    BackgroundTasks vs asyncio.create_task:
    - BackgroundTasks é gerenciado pelo FastAPI — garante execução após o response
    - create_task pode ser cancelado se o event loop for resetado
    """

    # ── PASSO 1: Lê o body bruto ──────────────────────────────────────────────
    try:
        raw_body = await request.body()
        body_str = raw_body.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"[WEBHOOK] Falha ao ler body da requisição: {e}")
        return JSONResponse({"status": "error", "detail": "cannot_read_body"}, status_code=200)

    # logger.info(f"[WEBHOOK] ← Body recebido: {body_str[:300]}")  # Descomente se precisar debugar muito a fundo

    # ── PASSO 2: Parse JSON ───────────────────────────────────────────────────
    try:
        body_dict = json.loads(body_str)
    except json.JSONDecodeError as e:
        logger.error(f"[WEBHOOK] JSON inválido: {e} | body={body_str[:200]}")
        return JSONResponse({"status": "ignored", "reason": "invalid_json"}, status_code=200)

    # ── PASSO 3: Validação Pydantic ───────────────────────────────────────────
    # BUG CORRIGIDO: usar model_validate(dict) em vez de **dict
    # WAHAWebhook(**body_dict) explode porque 'from' é palavra reservada Python
    try:
        webhook = WAHAWebhook.model_validate(body_dict)
    except Exception as e:
        logger.error(f"[WEBHOOK] Falha na validação Pydantic: {e} | body={body_str[:300]}")
        return JSONResponse({"status": "ignored", "reason": "validation_error"}, status_code=200)

    # ── PASSO 4: Filtros ──────────────────────────────────────────────────────
    ignore, reason = _should_ignore(webhook)
    if ignore:
        # Só gera log de aviso se não for um evento silencioso do sistema (como ack de leitura)
        if not reason.startswith("ignored_event_"):
            logger.info(f"[WEBHOOK] Ignorado → motivo: {reason}")
        return JSONResponse({"status": "ignored", "reason": reason})

    # Logamos apenas eventos que passaram pelos filtros
    logger.info(
        f"[WEBHOOK] Evento={webhook.event} | "
        f"De={webhook.payload.from_} | "
        f"Para={webhook.payload.to} | "
        f"hasMedia={webhook.payload.hasMedia} | "
        f"body='{(webhook.payload.body or '')[:60]}'"
    )

    # ── PASSO 5: Extrai dados úteis ───────────────────────────────────────────
    payload = webhook.payload
    phone = payload.from_
    name = (
        payload.data_.notifyName
        if payload.data_ and payload.data_.notifyName
        else phone
    )
    message_id = payload.id or ""

    logger.info(f"[WEBHOOK] ✅ Mensagem aceita | phone={phone} | nome={name}")

    # ── PASSO 6: Agenda processamento em background ───────────────────────────
    background_tasks.add_task(
        _process_message,
        phone=phone,
        name=name,
        message_id=message_id,
        body=payload.body,
        has_media=payload.hasMedia,
    )

    return JSONResponse({"status": "received", "phone": phone})


# ─────────────────────────────────────────────────────────────────────────────
# Processamento em background
# ─────────────────────────────────────────────────────────────────────────────

async def _process_message(
    phone: str,
    name: str,
    message_id: str,
    body: str | None,
    has_media: bool,
) -> None:
    """
    Fluxo completo:
      1. Texto ou Áudio → texto final
      2. Texto → LLM Groq → resposta
      3. Typing → send_text via WAHA
    Cada etapa tem log próprio para facilitar debug.
    """

    # ── ETAPA 1: Resolve texto ────────────────────────────────────────────────
    try:
        if has_media:
            logger.info(f"[{phone}] 🎤 Áudio detectado — baixando mídia (message_id={message_id})...")
            audio_bytes = await waha_service.download_media(phone, message_id)
            logger.info(f"[{phone}] 🎤 Áudio baixado ({len(audio_bytes)} bytes) — enviando para Whisper...")
            user_text = await groq_service.transcribe_audio(audio_bytes)
            logger.info(f"[{phone}] 🎤 Transcrição: '{user_text}'")
        else:
            user_text = (body or "").strip()
            logger.info(f"[{phone}] 💬 Texto recebido: '{user_text}'")
    except Exception as e:
        logger.error(f"[{phone}] ❌ ETAPA 1 (resolver texto) falhou: {e}", exc_info=True)
        return

    if not user_text:
        logger.warning(f"[{phone}] ⚠️ Texto vazio após processamento — ignorando")
        return

    # ── ETAPA 2: LLM ─────────────────────────────────────────────────────────
    try:
        logger.info(f"[{phone}] 🤖 Enviando para Groq LLM: '{user_text[:80]}'")
        response_text = await groq_service.get_llm_response(phone, user_text)
        logger.info(f"[{phone}] 🤖 Resposta Groq ({len(response_text)} chars): '{response_text[:100]}...'")
    except Exception as e:
        logger.error(f"[{phone}] ❌ ETAPA 2 (Groq LLM) falhou: {e}", exc_info=True)
        try:
            await waha_service.send_text(phone, "⚠️ Erro interno. Tente novamente.")
        except Exception:
            pass
        return

    # ── ETAPA 3: Envia resposta via WAHA ──────────────────────────────────────
    try:
        logger.info(f"[{phone}] 📤 Enviando typing...")
        await waha_service.send_typing(phone)

        logger.info(f"[{phone}] 📤 Enviando mensagem via WAHA...")
        await waha_service.send_text(phone, response_text)
        logger.info(f"[{phone}] ✅ Mensagem enviada com sucesso!")
    except Exception as e:
        logger.error(f"[{phone}] ❌ ETAPA 3 (WAHA send) falhou: {e}", exc_info=True)