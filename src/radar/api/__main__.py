"""Run the Control Center API locally (``python -m radar.api`` / ``radar-api``)."""

from __future__ import annotations

import uvicorn

from radar.application.correlation import bind_correlation_id
from radar.domain.config import ConfigInvalidError
from radar.infrastructure.config import ConfigLoader
from radar.infrastructure.logging import configure_logging, get_logger

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8000


def main() -> None:
    bind_correlation_id()
    try:
        config = ConfigLoader.from_env().load()
    except ConfigInvalidError as exc:
        configure_logging("INFO")
        get_logger("api").error("configuração inválida", extra={"error_code": exc.error.code})
        raise SystemExit(1) from exc

    configure_logging(config.log_level)
    uvicorn.run(
        "radar.api.app:create_app",
        factory=True,
        host=LOCAL_HOST,
        port=LOCAL_PORT,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
