from app.dash_app import create_dash_app
from app.config import get_app_config


def run() -> None:
    config = get_app_config()
    app = create_dash_app()
    app.run(
        host=config.dash_host,
        port=config.dash_port,
        debug=config.debug,
        use_reloader=False,
    )


if __name__ == "__main__":
    run()
