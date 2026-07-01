from app.main import app


REQUIRED_PATHS = {
    "/api/v1/data/summary",
    "/api/v1/data/export/backup",
    "/api/v1/data/export/csv",
    "/api/v1/data/import/preview",
    "/api/v1/data/import/apply",
    "/api/v1/data/clear-financial",
    "/api/v1/data/account",
    "/api/v1/data/history",
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
        "Rotas de dados e backup "
        "registradas corretamente."
    )


if __name__ == "__main__":
    main()
