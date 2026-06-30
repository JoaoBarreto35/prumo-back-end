from app.main import app


REQUIRED_PATHS = {
    "/api/v1/transactions-bulk/preview",
    "/api/v1/transactions-bulk/apply",
}


def main() -> None:
    available = {
        route.path
        for route in app.routes
    }

    missing = (
        REQUIRED_PATHS
        - available
    )

    if missing:
        raise SystemExit(
            "Rotas ausentes: "
            + ", ".join(
                sorted(missing)
            )
        )

    print("IMPORT OK")
    print(
        "Rotas de ações em massa "
        "registradas corretamente."
    )


if __name__ == "__main__":
    main()
