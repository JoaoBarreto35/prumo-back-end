from app.main import app


REQUIRED_PATHS = {
    "/api/v1/closings",
    "/api/v1/closings/summary",
    "/api/v1/closings/month-status",
    "/api/v1/closings/{reference_month}/close",
    "/api/v1/closings/{reference_month}/reopen",
    "/api/v1/closings/{reference_month}/notes",
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
    print(
        "Rotas de fechamento registradas corretamente."
    )


if __name__ == "__main__":
    main()
