from app.main import app


REQUIRED_PATHS = {
    "/api/v1/admin/users",
    "/api/v1/admin/users/{user_id}/status",
    "/api/v1/admin/users/{user_id}/role",
    "/api/v1/admin/users/{user_id}/temporary-password",
    "/api/v1/admin/users/{user_id}/sessions",
    "/api/v1/admin/users/{user_id}/sessions/{session_id}",
    "/api/v1/admin/audit",
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
        "Rotas administrativas registradas corretamente."
    )


if __name__ == "__main__":
    main()
