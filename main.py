from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import requests
import os
import json
import time
import uuid
from dotenv import load_dotenv

# Carregar variáveis de ambiente do .env
load_dotenv()

SIMPLIFIQUE_API_URL = "https://app.simplifique.ai/pt/chatbot/api/v1/message/"
PORT = int(os.getenv("PORT", 8000))
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
BASE_USER_KEY = os.getenv("BASE_USER_KEY", "default_user")

# Inicialização do app
app = FastAPI(title="OpenAI Adapter → Simplifique.ai")

# Modelos
class Message(BaseModel):
    role: str
    content: str

class OpenAIRequest(BaseModel):
    model: str
    messages: List[Message]
    chatbot_uuid: Optional[str] = None
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    user_key: Optional[str] = None
    custom_base_system_prompt: Optional[str] = None
    recipent_url: Optional[str] = None

# Funções auxiliares
def extract_bearer_token(authorization: str):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Cabeçalho de autorização ausente ou inválido.")
    return authorization.split(" ")[1]

def extract_user_message(messages: List[Message]) -> str:
    return next((msg.content for msg in reversed(messages) if msg.role == "user"), None)

def extract_meta(messages: List[Message]) -> dict:
    meta = {}
    for msg in messages:
        if msg.role == "system" and msg.content.startswith("@meta:"):
            try:
                key, val = msg.content.replace("@meta:", "").split("=", 1)
                meta[key.strip()] = val.strip()
            except:
                continue
    return meta

def extract_prompt(messages: List[Message]) -> Optional[str]:
    return next((msg.content for msg in reversed(messages) if msg.role == "system" and not msg.content.startswith("@meta:")), None)

# Endpoint principal
@app.post("/v1/chat/completions")
async def chat_completions(request_data: OpenAIRequest, authorization: str = Header(None)):
    api_token = extract_bearer_token(authorization)

    # Extrair metadados ocultos do messages[]
    meta = extract_meta(request_data.messages)
    chatbot_uuid = request_data.chatbot_uuid or meta.get("chatbot_uuid") or request_data.model
    user_key = request_data.user_key or meta.get("user_key") or f"{BASE_USER_KEY}_{uuid.uuid4().hex[:8]}"
    prompt_customizado = request_data.custom_base_system_prompt or extract_prompt(request_data.messages)

    user_message = extract_user_message(request_data.messages)
    if not chatbot_uuid:
        raise HTTPException(status_code=400, detail="chatbot_uuid ausente (use campo model ou chatbot_uuid).")
    if not user_message:
        raise HTTPException(status_code=400, detail="Nenhuma mensagem do usuário encontrada.")

    payload = {
        "chatbot_uuid": chatbot_uuid,
        "user_key": user_key,
        "query": user_message
    }

    # Prompt customizado
    if prompt_customizado:
        payload["custom_base_system_prompt"] = prompt_customizado

    # Parâmetros opcionais
    if request_data.recipent_url:
        payload["recipent_url"] = request_data.recipent_url

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json"
    }

    if DEBUG_MODE:
        print("[Simplifique Payload] ->", json.dumps(payload))

    try:
        response = requests.post(SIMPLIFIQUE_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()

        if DEBUG_MODE:
            print("[Simplifique Response] ->", json.dumps(result))

        answer = (
            result.get("data", {}).get("answer")
            or result.get("response")
            or result.get("message")
            or "Desculpe, não entendi sua solicitação."
        )

        return JSONResponse({
            "id": f"chatcmpl-{uuid.uuid4().hex[:10]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": chatbot_uuid,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer
                    },
                    "finish_reason": "stop"
                }
            ]
        })

    except requests.RequestException as e:
        status = e.response.status_code if e.response else 502
        detail = e.response.json() if e.response else {"error": "Erro ao comunicar com a Simplifique"}
        if DEBUG_MODE:
            print("[ERRO API] ->", detail)
        raise HTTPException(status_code=status, detail=detail)

# Healthcheck
@app.get("/health")
async def health_check():
    return {"status": "ok", "api_version": "v1"}

@app.get("/")
async def root():
    return {
        "api": "OpenAI to Simplifique Adapter",
        "status": "running",
        "endpoints": {
            "chat_completions": "/v1/chat/completions"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print(f"Iniciando servidor na porta {PORT}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)


