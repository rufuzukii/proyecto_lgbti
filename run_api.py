from pathlib import Path
import sys

import uvicorn

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import get_app_config


if __name__ == "__main__":
    config = get_app_config()
    uvicorn.run(
        "app.api:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.local_mode,
    )

