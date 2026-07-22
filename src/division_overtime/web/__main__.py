from __future__ import annotations

import uvicorn

from division_overtime.web.config import load_web_config


def main() -> None:
    config = load_web_config()
    uvicorn.run(
        "division_overtime.web.app:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
