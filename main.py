from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from typing import List, Optional
import requests
import os
import json
import time
import uuid
import logging
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Carregar variáveis de ambiente do .env
load_dotenv()

SIMPLIFIQUE_API_URL = "https://app.simplifique.ai/pt/chatbot/api/v1/message/"
PORT = int(os.getenv("PORT", 8000))
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
BASE_USER_KEY = os.getenv("BASE_USER_KEY", "default_user")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Configuração de logging detalhado
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Inicialização do app FastAPI com CORS
app = FastAPI(
    title="OpenAI Adapter → Simplifique.ai",
    description="Gateway compatível OpenAI para Simplifique.ai (Stammer). Plug & play para n8n, LangChain e outros.",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models para validação de entrada
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

def extract_bearer_token(authorization: str) -> str:
    """Extrai o token Bearer do header Authorization."""
    if not authorization or not authorization.lower().startswith("bearer "):
        logging.warning("Requisição sem Bearer token.")
        raise HTTPException(status_code=401, detail="Cabeçalho de autorização ausente ou inválido. Use Bearer <API_KEY>.")
    return authorization.split(" ")[1]

def extract_user_message(messages: List[Message]) -> str:
    """Encontra a última mensagem do usuário com role 'user'."""
    for msg in reversed(messages):
        if hasattr(msg, 'role') and hasattr(msg, 'content') and msg.role == "user":
            return msg.content
    raise HTTPException(status_code=400, detail="Nenhuma mensagem do usuário encontrada ou payload malformado.")

def extract_meta(messages: List[Message]) -> dict:
    """Extrai metadados passados via mensagens system."""
    meta = {}
    for msg in messages:
        if msg.role == "system" and msg.content.startswith("@meta:"):
            try:
                key, val = msg.content.replace("@meta:", "").split("=", 1)
                meta[key.strip()] = val.strip()
            except Exception:
                continue
    return meta

def extract_prompt(messages: List[Message]) -> Optional[str]:
    """Pega o último prompt customizado das mensagens system."""
    return next((msg.content for msg in reversed(messages) if msg.role == "system" and not msg.content.startswith("@meta:")), None)

def get_requests_session() -> requests.Session:
    """Cria uma sessão requests com retry e timeout."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.7,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

# Endpoint principal
@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str = Header(None)):
    try:
        # Leitura e logging do payload recebido
        raw_body = await request.body()
        if DEBUG_MODE:
            logging.info(f"Payload recebido: {raw_body.decode('utf-8', errors='ignore')}")

        # Validação e parsing do payload
        try:
            request_data = OpenAIRequest.parse_raw(raw_body)
        except ValidationError as ve:
            logging.warning(f"Payload inválido: {ve.errors()}")
            raise HTTPException(status_code=422, detail="Payload inválido ou campos obrigatórios ausentes.")

        # Autenticação
        api_token = extract_bearer_token(authorization)

        # Extração dos campos principais
        meta = extract_meta(request_data.messages)
        chatbot_uuid = request_data.chatbot_uuid or meta.get("chatbot_uuid") or request_data.model
        user_key = request_data.user_key or meta.get("user_key") or f"{BASE_USER_KEY}_{uuid.uuid4().hex[:8]}"
        prompt_customizado = request_data.custom_base_system_prompt or extract_prompt(request_data.messages)
        user_message = extract_user_message(request_data.messages)

        if not chatbot_uuid:
            raise HTTPException(status_code=400, detail="chatbot_uuid ausente (use campo model ou chatbot_uuid).")

        # Montagem do payload para Simplifique
        payload = {
            "chatbot_uuid": chatbot_uuid,
            "user_key": user_key,
            "query": user_message
        }
        if prompt_customizado:
            payload["custom_base_system_prompt"] = prompt_customizado
        if request_data.recipent_url:
            payload["recipent_url"] = request_data.recipent_url

        headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json"
        }

        logging.info(f"Enviando para Simplifique: {json.dumps(payload, ensure_ascii=False)}")
        logging.info(f"Headers: {headers}")

        # Request para Simplifique com retry e timeout
        session = get_requests_session()
        try:
            response = session.post(SIMPLIFIQUE_API_URL, json=payload, headers=headers, timeout=20)
        except Exception as e:
            logging.error(f"Erro de conexão com Simplifique: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Erro de conexão com a Simplifique.ai: {str(e)}")

        logging.info(f"Resposta da Simplifique: {response.status_code} | {response.text}")

        # Processamento da resposta
        try:
            result = response.json()
        except Exception:
            logging.error(f"Resposta não JSON recebida da Simplifique: {response.text}")
            raise HTTPException(status_code=502, detail="Resposta não JSON recebida do Simplifique.ai.")

        if response.status_code not in (200, 201, 202):
            detail = result.get('message') or result.get('error') or result
            logging.warning(f"Erro da API Simplifique: {detail}")
            raise HTTPException(status_code=response.status_code, detail=f"Erro Simplifique: {detail}")

        answer = (
            result.get("data", {}).get("answer")
            or result.get("response")
            or result.get("message")
            or "Desculpe, não entendi sua solicitação."
        )

        logging.info(f"Chatbot: {chatbot_uuid} | User: {user_key} | Request concluída com sucesso.")

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

    except HTTPException as he:
        logging.error(f"HTTPException: {he.detail}")
        raise he
    except Exception as e:
        logging.exception(f"Erro inesperado: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno inesperado: {str(e)}")

# Healthcheck endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "api_version": "v1"}

# Endpoint raiz com descrição dos endpoints
@app.get("/")
async def root():
    return {
        "api": "OpenAI to Simplifique Adapter",
        "status": "running",
        "endpoints": {
            "chat_completions": "/v1/chat/completions"
        }
    }

# Inicializador para ambiente standalone (Railway/Heroku/docker)
if __name__ == "__main__":
    import uvicorn
    logging.info(f"Iniciando servidor na porta {PORT}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)





