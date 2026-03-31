# app/main.py

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import webhook


# Logging detalhado no terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("groq").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("FRAN v2.0 iniciando...")
    logger.info("  Webhook:  POST /api/webhook")
    logger.info("  Health:   GET  /health")
    logger.info("  Docs:     GET  /docs")
    logger.info("=" * 60)
    yield
    logger.info("FRAN v2.0 encerrado.")


app = FastAPI(
    title="FRAN - Assistente Virtual de Saude",
    description="Chatbot WhatsApp da Rede Municipal de Saude de Afranio (PE)",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(webhook.router)


@app.get("/health", tags=["infra"])
async def health_check():
    """Endpoint de monitoramento."""
    return {"status": "ok", "service": "FRAN", "version": "2.0.0"}
