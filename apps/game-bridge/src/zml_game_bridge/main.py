from __future__ import annotations

import uvicorn

from zml_game_bridge.settings import Settings, configure_logging_from_env


def main() -> None:
    configure_logging_from_env()
    s = Settings()
    # Uvicorn factory: module:function + factory=True
    uvicorn.run(
        "zml_game_bridge.api.app:create_app",
        factory=True,
        host=s.host,
        port=s.port,
        reload=s.reload,
    )


if __name__ == "__main__":
    main()
