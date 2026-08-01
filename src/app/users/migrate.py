import logging

from app.logging_config import configure_secure_logging
from app.users.service import migrate_legacy_user_types


def main() -> None:
    configure_secure_logging()
    updated = migrate_legacy_user_types()
    logging.getLogger(__name__).info(
        "user_type_migration_completed",
        extra={"updated_rows": updated},
    )


if __name__ == "__main__":
    main()
