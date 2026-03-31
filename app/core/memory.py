# app/core/memory.py

from collections import defaultdict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from app.core.config import settings


# defaultdict: se a chave (phone) não existir, cria automaticamente uma lista vazia.
# Isso substitui o "contexto de sessão" que o Dialogflow gerenciava internamente.
# Estrutura: { "5587999999999@c.us": [HumanMessage(...), AIMessage(...), ...] }
_store: dict[str, list[BaseMessage]] = defaultdict(list)


def add_turn(phone: str, human_text: str, ai_text: str) -> None:
    """
    Adiciona um turno completo (pergunta + resposta) ao histórico do usuário.
    Mantém apenas os últimos N turnos para não estourar o context window da LLM.
    """
    history = _store[phone]
    history.append(HumanMessage(content=human_text))
    history.append(AIMessage(content=ai_text))

    # Cada "turno" = 2 mensagens (human + ai). Mantemos só os últimos N turnos.
    max_messages = settings.memory_max_turns * 2
    if len(history) > max_messages:
        # Remove as mensagens mais antigas (início da lista)
        _store[phone] = history[-max_messages:]


def get_history(phone: str) -> list[BaseMessage]:
    """Retorna o histórico de mensagens de um usuário."""
    return _store[phone]


def clear_history(phone: str) -> None:
    """Limpa o histórico quando o usuário digita SAIR/X."""
    if phone in _store:
        del _store[phone]
