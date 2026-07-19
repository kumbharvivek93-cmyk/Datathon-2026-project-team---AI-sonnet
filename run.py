"""Development entry point and WSGI application export."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_RUN_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
