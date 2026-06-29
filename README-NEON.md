# Prumo + Neon

Este pacote adapta o backend do Prumo para trabalhar com Neon Postgres.

## 1. Obter a URL

No painel do Neon:

1. Abra o projeto.
2. Clique em **Connect**.
3. Selecione o banco e a branch.
4. Copie a connection string.
5. Para manter apenas uma `DATABASE_URL`, prefira inicialmente a conexão **Direct**.

A URL normalmente será parecida com:

```env
DATABASE_URL=postgresql://usuario:senha@ep-exemplo.us-east-2.aws.neon.tech/prumo?sslmode=require
```

O `settings.py` converte automaticamente:

```text
postgresql://
```

para:

```text
postgresql+psycopg://
```

Não altere manualmente a URL copiada do Neon.

## 2. Criar o `.env`

Copie:

```powershell
Copy-Item .env.example .env
```

Preencha:

```env
DATABASE_URL=...
JWT_SECRET=...
GEMINI_API_KEY=...
```

O `.env` não deve ser enviado ao GitHub.

## 3. Gerar o JWT_SECRET

No PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copie o resultado para `JWT_SECRET`.

## 4. Instalar

```powershell
pip install -r requirements-neon.txt
pip freeze > requirements.txt
```

## 5. Testar conexão

```powershell
python -m scripts.test_database
```

## 6. Gerar e aplicar a migration

Caso ainda não tenha gerado:

```powershell
alembic revision --autogenerate -m "create financial core tables"
alembic upgrade head
```

Caso a migration já exista, execute apenas:

```powershell
alembic upgrade head
```

## 7. Seed

```powershell
python -m scripts.seed
```

## 8. Rodar

```powershell
fastapi dev
```

Teste:

```text
http://127.0.0.1:8000/api/v1/health
```

Resposta esperada:

```json
{
  "status": "ok",
  "service": "Prumo API",
  "version": "0.1.0",
  "environment": "development",
  "database": {
    "status": "ok"
  }
}
```

## Segurança

Nunca coloque no front-end:

- `DATABASE_URL`;
- `JWT_SECRET`;
- `GEMINI_API_KEY`.

Esses valores pertencem exclusivamente ao backend e às variáveis do serviço de deploy.
