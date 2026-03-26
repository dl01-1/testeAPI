import os
import google.generativeai as genai
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# 1. Configuração básica
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# 2. Inicializamos o modelo (Gemini 2.5 Flash é ótimo para chatbots)
model = genai.GenerativeModel('gemini-2.5-flash')

app = FastAPI()

class Mensagem(BaseModel):
    texto: str

@app.post("/chat123")
async def falar_com_ai(dados: Mensagem):
    # 3. Enviando a pergunta para a IA
    response = model.generate_content(dados.texto)
    
    # 4. Retornando a resposta real gerada pelo Gemini
    return {
        "resposta_ia": response.text,
        "modelo": "Gemini 2.5 Flash"
    }