from app.main import app


REQUIRED_PATHS = {
    "/api/v1/accounts",
    "/api/v1/accounts/{account_id}",
    "/api/v1/accounts/{account_id}/impact",
    "/api/v1/accounts/{account_id}/default",
    "/api/v1/accounts/{account_id}/activate",
    "/api/v1/accounts/{account_id}/archive",
    "/api/v1/accounts/{account_id}/transfer",
    "/api/v1/accounts/{account_id}/delete",
    "/api/v1/categories",
    "/api/v1/categories/{category_id}",
    "/api/v1/categories/{category_id}/impact",
    "/api/v1/categories/{category_id}/activate",
    "/api/v1/categories/{category_id}/archive",
    "/api/v1/categories/{category_id}/transfer",
    "/api/v1/categories/{category_id}/delete",
}


def main() -> None:
    available = {
        route.path
        for route in app.routes
    }

    missing = REQUIRED_PATHS - available

    if missing:
        raise SystemExit(
            "Rotas ausentes: "
            + ", ".join(sorted(missing))
        )

    print("IMPORT OK")
    print("CRUD de contas e categorias registrado corretamente.")


if __name__ == "__main__":
    main()
