from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("zml_game_bridge.app:app", host="127.0.0.1", port=17171, reload=True)


if __name__ == "__main__":
    main()