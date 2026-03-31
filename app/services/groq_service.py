# app/services/groq_service.py

import httpx
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.config import settings
from app.core.memory import get_history, add_turn, clear_history
from app.data.knowledge_base import SYSTEM_PROMPT


# --- Inicializa o modelo LLM ---
# ChatGroq é o wrapper LangChain para a API da Groq.
# llama-3.3-70b-versatile: excelente custo-benefício para português.
# temperature=0.3: respostas mais consistentes/factuais (0=determinístico, 1=criativo)
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    api_key=settings.groq_api_key,
)

# --- Monta o prompt template ---
# MessagesPlaceholder("history") = onde o LangChain injeta o histórico da conversa.
# Isso substitui o gerenciamento de contexto que o Dialogflow fazia com "lifespan".
prompt_template = ChatPromptTemplate.from_messages([
    SystemMessage(content=SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}"),
])

# --- Chain LCEL (LangChain Expression Language) ---
# O operador | (pipe) encadeia: prompt → llm
# Isso é o padrão moderno do LangChain — substituiu as classes Chain legadas.
chain = prompt_template | llm


async def get_llm_response(phone: str, user_text: str) -> str:
    """
    Processa a mensagem do usuário e retorna a resposta da FRAN.

    Fluxo:
    1. Recupera histórico da conversa deste usuário
    2. Monta o prompt com histórico + nova mensagem
    3. Envia para Groq (async)
    4. Salva o turno no histórico
    5. Retorna o texto da resposta

    Args:
        phone: identificador único do usuário (número@c.us)
        user_text: texto transcrito (ou digitado) pelo usuário
    """
    # Verifica comandos de encerramento ANTES de chamar a LLM (economia de tokens)
    normalized = user_text.strip().upper()
    if normalized in {"X", "SAIR", "ENCERRAR", "SAIR.", "X."}:
        clear_history(phone)
        farewell = (
            "✅ *Atendimento Concluído*\n\n"
            "Gostaria de nos avaliar? Digite *10* e deixe sua nota. ⭐\n\n"
            "Agradecemos o contato! O canal da *Saúde de Afrânio* segue à sua "
            "disposição 24 horas por dia. 🟢⚪\n\n"
            "*Até a próxima e cuide de sua saúde!* 🩺✨"
        )
        return farewell

    # Recupera histórico do usuário (lista de HumanMessage/AIMessage)
    history: list[BaseMessage] = get_history(phone)

    # Invoca a chain de forma assíncrona — não bloqueia o servidor
    response = await chain.ainvoke({
        "history": history,
        "input": user_text,
    })

    ai_text: str = response.content

    # Persiste o turno no histórico para a próxima mensagem
    add_turn(phone, user_text, ai_text)

    return ai_text


async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcreve um áudio OGG para texto usando Groq Whisper.
    Substitui o nó 'Grok' do n8n (que já usava whisper-large-v3-turbo).

    Usamos httpx diretamente aqui porque a API de transcrição é multipart/form-data,
    diferente do endpoint de chat — o SDK da Groq não tem wrapper async para isso.

    Args:
        audio_bytes: conteúdo binário do arquivo OGG

    Returns:
        Texto transcrito
    """
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    # Enviamos o arquivo com nome "audio.ogg" — igual ao nó 'Code in JavaScript' do n8n
    files = {"file": ("audio.ogg", audio_bytes, "audio/ogg")}
    data = {
        "model": "whisper-large-v3-turbo",
        "language": "pt",  # força português — melhora precisão
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        result = response.json()
        return result.get("text", "").strip()
