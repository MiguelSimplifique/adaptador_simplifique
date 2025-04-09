# Adaptador OpenAI → Stammer

Este projeto implementa um servidor intermediário (adaptador) que simula a API da OpenAI (`/v1/chat/completions`) e redireciona as requisições para a API do **Stammer.ai**, convertendo os formatos e autenticando as chamadas.

## Funcionalidades

- Expõe um endpoint que simula a API OpenAI de chat completions
- Autentica as requisições com um token privado
- Valida os UUIDs dos chatbots permitidos
- Converte o formato da requisição OpenAI para o formato Stammer
- Converte a resposta Stammer para o formato OpenAI
- Pronto para deploy no Railway

## Pré-requisitos

- Python 3.8+
- pip (gerenciador de pacotes Python)

## Configuração

1. Clone este repositório
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Crie um arquivo `.env` baseado no `.env.example`:
   ```bash
   cp .env.example .env
   ```
4. Configure suas variáveis de ambiente no arquivo `.env`:
   - `ACCESS_TOKEN`: Token para autenticação das chamadas ao adaptador
   - `STAMMER_API_KEY`: Token usado para autenticar no Stammer.ai
   - `ALLOWED_CHATBOT_UUIDS`: Lista de `chatbot_uuid` válidos (separados por vírgula)
   - `BASE_USER_KEY`: Valor base ou fixo para o campo `user_key`
   - `PORT`: Porta para rodar no Railway (default: 8000)

## Executando localmente

Para iniciar o servidor localmente:

```bash
uvicorn main:app --reload
```

O servidor estará disponível em http://localhost:8000.

## Como usar

Envie requisições para o endpoint `/v1/chat/completions` no formato OpenAI:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [
      {"role": "system", "content": "Você é um assistente"},
      {"role": "user", "content": "Olá!"}
    ],
    "chatbot_uuid": "uuid-do-meu-bot"
  }'
```

## Deploy no Railway

Este projeto está configurado para ser facilmente implantado no Railway:

1. Conecte seu repositório ao Railway
2. Configure as variáveis de ambiente no painel do Railway
3. O Railway detectará automaticamente o `Procfile` e iniciará a aplicação

## Estrutura do Projeto

- `main.py` - Código principal do adaptador
- `requirements.txt` - Dependências do projeto
- `Procfile` - Configuração para deploy no Railway
- `.env.example` - Exemplo de arquivo de variáveis de ambiente
- `.gitignore` - Arquivos a serem ignorados pelo git
- `README.md` - Este arquivo de documentação

## Notas

- Apenas a última mensagem do usuário é enviada para o Stammer
- As mensagens de sistema (role: "system") são ignoradas
- O parâmetro `user_key` enviado ao Stammer é gerado com base no `BASE_USER_KEY` + um identificador único
