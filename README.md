# Prumo API — Backend completo

Backend pronto para o escopo atual do Prumo.

## Incluído

- FastAPI;
- Neon PostgreSQL;
- criação automática das tabelas;
- usuário administrador inicial;
- cadastro com status pendente;
- login JWT;
- refresh token;
- sessões;
- contas;
- categorias;
- grupos avulsos, parcelados e recorrentes;
- geração mensal;
- recorrências com janela futura;
- transações;
- atualização de status;
- fechamento mensal;
- administração;
- Gemini/Lume;
- health check;
- Swagger.

## 1. Ambiente

Python 3.11 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. `.env`

Copie:

```powershell
Copy-Item .env.example .env
```

Preencha `DATABASE_URL`, `JWT_SECRET` e `GEMINI_API_KEY`.

Para gerar o segredo:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 3. Rodar

```powershell
fastapi dev
```

Ao iniciar, o backend:

1. conecta ao Neon;
2. cria as tabelas que ainda não existem;
3. cria um administrador inicial caso nenhum exista;
4. cria PIX e categorias padrão para o administrador.

## Administrador inicial

```text
E-mail: admin@prumo.local
Senha: Prumo123
```

O usuário é marcado para troca obrigatória de senha. Troque essas credenciais antes do deploy.

## Endereços

```text
API: http://127.0.0.1:8000
Swagger: http://127.0.0.1:8000/docs
Health: http://127.0.0.1:8000/api/v1/health
```

## Fluxo para testar

1. Abra `/docs`.
2. Execute `POST /api/v1/auth/login` com o administrador.
3. Copie `access_token`.
4. Clique em **Authorize**.
5. Use `Bearer SEU_TOKEN`.
6. Teste contas, categorias e grupos.

## Exemplo de grupo avulso

```json
{
  "group_type": "single",
  "transaction_type": "expense",
  "description": "Mercado",
  "account_id": "UUID_DA_CONTA",
  "category_id": "UUID_DA_CATEGORIA",
  "amount": 350,
  "start_date": "2026-06-29",
  "is_indefinite": false,
  "origin": "manual"
}
```

## Exemplo parcelado

O valor informado é o total.

```json
{
  "group_type": "installment",
  "transaction_type": "expense",
  "description": "Motor",
  "account_id": "UUID_DA_CONTA",
  "category_id": "UUID_DA_CATEGORIA",
  "amount": 6000,
  "occurrence_count": 10,
  "start_date": "2026-06-29",
  "is_indefinite": false,
  "origin": "manual"
}
```

## Exemplo recorrente

```json
{
  "group_type": "recurring",
  "transaction_type": "expense",
  "description": "Internet",
  "account_id": "UUID_DA_CONTA",
  "category_id": "UUID_DA_CATEGORIA",
  "amount": 99.9,
  "start_date": "2026-06-29",
  "is_indefinite": true,
  "origin": "manual"
}
```

## Observação importante

`create_all()` cria tabelas ausentes, mas não altera com segurança tabelas existentes quando models mudam. O backend está pronto para o modelo atual. Quando a estrutura do banco evoluir, use migrations.
