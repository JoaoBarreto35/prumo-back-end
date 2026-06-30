from app.main import app


REQUIRED_PATHS = {
    "/api/v1/lume/conversations",
    "/api/v1/lume/conversations/{conversation_id}/messages",
    "/api/v1/lume/message",
    "/api/v1/lume/actions/{message_id}/confirm",
    "/api/v1/lume/actions/{message_id}/cancel",
    "/api/v1/lume/summary",
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
            + ", ".join(
                sorted(missing)
            )
        )

    print("IMPORT OK")
    print(
        "Rotas do Lume registradas "
        "corretamente."
    )


if __name__ == "__main__":
    main()
