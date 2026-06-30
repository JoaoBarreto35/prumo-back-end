from app.main import app


REQUIRED_PATHS = {
    "/api/v1/settings/profile",
    "/api/v1/settings/preferences",
    "/api/v1/settings/security",
    "/api/v1/settings/password",
    "/api/v1/settings/sessions/others",
    "/api/v1/settings/sessions/{session_id}",
}


def main() -> None:
    available = {
        route.path
        for route in app.routes
    }

    missing = (
        REQUIRED_PATHS - available
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
        "Rotas de configurações "
        "registradas corretamente."
    )


if __name__ == "__main__":
    main()
