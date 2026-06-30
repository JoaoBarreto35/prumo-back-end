from app.main import app


REQUIRED_PATHS = {
    "/api/v1/notifications",
    "/api/v1/notifications/unread-count",
    "/api/v1/notifications/sync",
    "/api/v1/notifications/{notification_id}/read",
    "/api/v1/notifications/read-all",
    "/api/v1/notifications/{notification_id}/snooze",
    "/api/v1/notifications/{notification_id}",
    "/api/v1/notifications/preferences/me",
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
        "Rotas de notificações registradas corretamente."
    )


if __name__ == "__main__":
    main()
