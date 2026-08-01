import logging

from app.config import get_app_config
from app.dash_app import create_dash_app
from app.users.service import migrate_legacy_user_types

logger = logging.getLogger(__name__)


def run() -> None:
    config = get_app_config()
    try:
        migrate_legacy_user_types()
    except Exception:
        logger.warning("legacy_user_type_migration_failed", exc_info=True)
    app = create_dash_app()
    app.run(
        host=config.dash_host,
        port=config.dash_port,
        debug=config.debug,
        use_reloader=False,
    )


if __name__ == "__main__":
    run()
