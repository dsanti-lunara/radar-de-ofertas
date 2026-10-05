"""Run the Control Center API locally (``python -m radar.api`` / ``radar-api``)."""

from __future__ import annotations

import uvicorn

from radar.infrastructure.settings import Settings

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8000


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "radar.api.app:create_app",
        factory=True,
        host=LOCAL_HOST,
        port=LOCAL_PORT,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
