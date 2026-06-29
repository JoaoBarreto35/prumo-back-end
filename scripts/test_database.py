from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    version() AS database_version
                """
            )
        ).mappings().one()

        print("Conexão com o Neon realizada com sucesso.")
        print(f"Banco: {result['database_name']}")
        print(f"Usuário: {result['database_user']}")
        print(f"Versão: {result['database_version']}")


if __name__ == "__main__":
    main()
