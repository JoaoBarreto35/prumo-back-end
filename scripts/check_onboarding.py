from app.main import app


REQUIRED_PATHS = {
    "/api/v1/onboarding",
    "/api/v1/onboarding/progress",
    "/api/v1/onboarding/complete",
    "/api/v1/onboarding/skip",
    "/api/v1/onboarding/restart",
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
        "Rotas de onboarding "
        "registradas corretamente."
    )


if __name__ == "__main__":
    main()
