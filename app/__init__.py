"""Flask application factory for the Crime Intelligence platform."""

from __future__ import annotations

import os
from importlib import import_module

from flask import Flask, redirect, url_for
from werkzeug.routing import BuildError

from config import Config, get_config

from app.extensions import db, init_extensions


def _register_optional_blueprint(app: Flask, module_name: str, blueprint_name: str) -> None:
    """Register a feature blueprint when that feature package is installed.

    During incremental development, only an absent feature module is ignored.
    Errors raised *inside* an existing module continue to fail loudly.
    """
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as error:
        package_name = module_name.rsplit(".", 1)[0]
        if error.name in {module_name, package_name}:
            return
        raise

    blueprint = getattr(module, blueprint_name)
    app.register_blueprint(blueprint)


def _register_blueprints(app: Flask) -> None:
    """Register built-in and independently developed feature blueprints."""
    from app.auth import auth_bp

    app.register_blueprint(auth_bp)
    for module_name, blueprint_name in (
        ("app.dashboard.routes", "dashboard_bp"),
        ("app.api.routes", "api_bp"),
        ("app.analytics.routes", "analytics_bp"),
        ("app.network.routes", "network_bp"),
        ("app.prediction.routes", "prediction_bp"),
        ("app.reports.routes", "reports_bp"),
    ):
        _register_optional_blueprint(app, module_name, blueprint_name)


def _bootstrap_database(app: Flask) -> None:
    """Initialize a local database and optional demo admin when configured."""
    # Importing models here registers their SQLAlchemy metadata for migrations.
    from app import models as _models  # noqa: F401
    from app.services.security import seed_demo_admin

    with app.app_context():
        if app.config["AUTO_CREATE_DB"]:
            db.create_all()
        if app.config["SEED_DEMO_ADMIN"]:
            seed_demo_admin()


def _register_commands(app: Flask) -> None:
    """Expose deliberate local-data initialization as a Flask CLI command."""
    import click
    from app.utils.seed import seed_demo_data

    @app.cli.command("seed-demo")
    @click.option("--force", is_flag=True, help="Replace existing fictional demo records.")
    def seed_demo_command(force: bool) -> None:
        """Create the fictional Karnataka demonstration dataset."""
        result = seed_demo_data(force=force)
        click.echo(f"Demo dataset ready: {result}")


def create_app(config_object: type[Config] | dict | str | None = None) -> Flask:
    """Create and configure an application instance.

    A named configuration (``development``, ``testing``, or ``production``),
    a config class, or an override mapping can be supplied by callers.
    """
    app = Flask(__name__, instance_relative_config=True)

    if isinstance(config_object, dict):
        app.config.from_object(get_config(os.getenv("FLASK_CONFIG")))
        app.config.from_mapping(config_object)
    elif isinstance(config_object, str):
        app.config.from_object(get_config(config_object))
    elif config_object is None:
        app.config.from_object(get_config(os.getenv("FLASK_CONFIG")))
    else:
        app.config.from_object(config_object)

    if app.config.get("APP_ENV") == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set when running in production.")

    init_extensions(app)
    _register_blueprints(app)
    _register_commands(app)

    @app.get("/")
    def index():
        """Send users to the dashboard when present, otherwise to sign-in."""
        try:
            return redirect(url_for("dashboard.index"))
        except BuildError:
            return redirect(url_for("auth.login"))

    _bootstrap_database(app)
    return app
