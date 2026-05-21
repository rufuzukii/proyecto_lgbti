from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.auth.app import create_auth_app
from app.config import get_app_config


if __name__ == "__main__":
    config = get_app_config()
    app = create_auth_app()
    app.run(host=config.auth_host, port=config.auth_port, debug=config.debug)
