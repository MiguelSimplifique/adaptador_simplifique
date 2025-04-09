from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import requests
import os
import json
import time
import uuid
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração da aplicação
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
STAMMER_API_KEY = os.getenv("STAMMER_API_KEY")
ALLOWED_CHATBOT_UUIDS = os.getenv("ALLOWED_CHATBOT_UUIDS", "").split(",")
BASE_USER_KEY = os.getenv("BASE_USER_KEY", "default_user")
PORT = int(os.getenv("PORT", 8000))

# URL da API do Stammer
STAMMER_API_URL = "https://app.simplifique.ai/pt/chatbot/api/v1/message/"

# Criação do app FastAPI
app = FastAPI(title="OpenAI to Stammer Adapter",
              description="Adaptador que converte chamadas da API OpenAI para a API do Stammer.ai")

# Modelos de dados para a API
class Message(BaseModel):
    role: str
    content: str

class OpenAIRequest(BaseModel):
    model: str
    messages: List[Message]
    chatbot_uuid: str
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None

# Funções auxiliares
def validate_token(authorization: str):
    """Valida o token de autorização"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorização não fornecido")
    
    token_parts = authorization.split()
    if len(token_parts) != 2 or token_parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Formato de token inválido. Use: Bearer TOKEN")
    
    token = token_parts[1]
    if token != ACCESS_TOKEN:
        print(f"Token inválido fornecido: {token}")
        raise HTTPException(status_code=401, detail="Token de autorização inválido")
    
    return True

def validate_chatbot_uuid(chatbot_uuid: str):
    """Valida se o UUID do chatbot está na lista de permitidos"""
    if not chatbot_uuid:
        raise HTTPException(status_code=400, detail="chatbot_uuid não fornecido")
    
    if chatbot_uuid not in ALLOWED_CHATBOT_UUIDS:
        print(f"UUID de chatbot não permitido: {chatbot_uuid}")
        raise HTTPException(status_code=403, detail="Chatbot UUID não autorizado")
    
    return True

def extract_user_message(messages: List[Message]) -> str:
    """Extrai a última mensagem do usuário da lista de mensagens"""
    user_messages = [msg.content for msg in messages if msg.role.lower() == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="Nenhuma mensagem do usuário encontrada")
    
    # Retorna a última mensagem do usuário
    return user_messages[-1]

# Endpoint principal que simula a API OpenAI
@app.post("/v1/chat/completions")
async def chat_completions(
    request_data: OpenAIRequest,
    authorization: str = Header(None)
):
    # Validar autenticação
    validate_token(authorization)
    
    # Validar UUID do chatbot
    validate_chatbot_uuid(request_data.chatbot_uuid)
    
    # Extrair mensagem do usuário
    user_message = extract_user_message(request_data.messages)
    
    # Gerar um identificador único para a requisição/usuário
    user_key = f"{BASE_USER_KEY}_{uuid.uuid4().hex[:8]}"
    
    # Preparar a requisição para o Stammer
    # Inclui parâmetros obrigatórios e opcionais conforme documentação
    stammer_payload = {
        "chatbot_uuid": request_data.chatbot_uuid,
        "user_key": user_key,
        "query": user_message
    }
    
    # Adicionar parâmetros opcionais se estiverem nas configurações
    recipient_url = os.getenv("RECIPIENT_URL")
    custom_base_prompt = os.getenv("CUSTOM_BASE_SYSTEM_PROMPT")
    
    if recipient_url:
        stammer_payload["recipent_url"] = recipient_url
        
    if custom_base_prompt:
        stammer_payload["custom_base_system_prompt"] = custom_base_prompt
    
    headers = {
        "Authorization": f"Token {STAMMER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Log para debug
    print(f"Enviando para Stammer: {json.dumps(stammer_payload)}")
    
    try:
        # Fazer a requisição para a API do Stammer
        response = requests.post(
            STAMMER_API_URL,
            json=stammer_payload,
            headers=headers
        )
        
        # Verificar se a requisição foi bem-sucedida
        response.raise_for_status()
        
        # Obter a resposta
        stammer_response = response.json()
        print(f"Resposta do Stammer: {json.dumps(stammer_response)}")
        
        # Extrair a resposta do assistente conforme documentação
        # A resposta está em stammer_response["data"]["answer"]
        if "data" in stammer_response and "answer" in stammer_response["data"]:
            assistant_response = stammer_response["data"]["answer"]
        else:
            # Fallback - tentar encontrar a resposta em outros campos possíveis
            assistant_response = (
                stammer_response.get("data", {}).get("answer", "") or 
                stammer_response.get("response", "") or 
                stammer_response.get("message", "")
            )
        
        # Formatar a resposta no formato OpenAI
        openai_format_response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:10]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request_data.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_response
                    },
                    "finish_reason": "stop"
                }
            ]
        }
        
        return JSONResponse(content=openai_format_response)
        
    except requests.exceptions.RequestException as e:
        print(f"Erro na comunicação com a API do Stammer: {str(e)}")
        
        # Se recebemos uma resposta com código de erro, incluir detalhes
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            try:
                error_detail = e.response.json()
                print(f"Detalhes do erro: {json.dumps(error_detail)}")
            except:
                error_detail = {"error": str(e)}
            
            raise HTTPException(status_code=status_code, detail=error_detail)
        else:
            # Erro genérico de comunicação
            raise HTTPException(status_code=502, detail={"error": "Erro ao comunicar com a API do Stammer"})

# Rota de verificação de saúde para o Railway
@app.get("/health")
async def health_check():
    return {"status": "ok", "api_version": "v1"}

# Rota raiz
@app.get("/")
async def root():
    return {
        "api": "OpenAI to Stammer Adapter",
        "status": "running",
        "endpoints": {
            "chat_completions": "/v1/chat/completions"
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Para execução direta do script
    print(f"Iniciando servidor na porta {PORT}")
    print(f"UUIDs de chatbots permitidos: {ALLOWED_CHATBOT_UUIDS}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
