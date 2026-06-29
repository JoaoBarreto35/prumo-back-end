# Banco de dados inicial do Prumo

## 1. Instale as dependências

```powershell
pip install -r requirements-database.txt
pip freeze > requirements.txt
```

## 2. Crie o banco PostgreSQL

```sql
CREATE DATABASE prumo;
```

## 3. Adicione ao `.env`

```env
DATABASE_URL=postgresql+psycopg://postgres:SUA_SENHA@localhost:5432/prumo
```

## 4. Teste a conexão

```powershell
python -m scripts.test_database
```

## 5. Gere a primeira migration

```powershell
alembic revision --autogenerate -m "create financial core tables"
```

Revise o arquivo criado em `alembic/versions`.

## 6. Aplique a migration

```powershell
alembic upgrade head
```

## 7. Execute o seed

```powershell
python -m scripts.seed
```

## Modelo

```text
users
├── accounts
├── categories
└── transaction_groups
    └── transactions
```

## Regras aplicadas

- UUID como chave;
- `Numeric(14, 2)` para dinheiro;
- valor sempre positivo;
- receita/despesa pelo tipo;
- toda transação pertence a um grupo;
- exclusão de grupo remove transações;
- conta e categoria usadas ficam protegidas por `RESTRICT`;
- descrição, conta, categoria e tipo são duplicados nas transações;
- regras de geração mensal ficam nos services, não nos models.
