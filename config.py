"""Application configuration for the Crime Intelligence platform."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Parse common environment-variable boolean values."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _database_url() -> str:
    """Return a SQLAlchemy URL, supporting Heroku-style postgres URLs."""
    default_url = f"sqlite:///{BASE_DIR / 'crime_intelligence.db'}"
    database_url = os.getenv("DATABASE_URL", default_url)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Config:
    """Base configuration shared by every environment."""

    APP_ENV = os.getenv("APP_ENV", "development").lower()
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret-key")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SESSION_COOKIE_SECURE"))
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = 3600

    AUTO_CREATE_DB = _as_bool(os.getenv("AUTO_CREATE_DB"), False)
    SEED_DEMO_ADMIN = _as_bool(os.getenv("SEED_DEMO_ADMIN"), False)
    DEMO_ADMIN_USERNAME = os.getenv("DEMO_ADMIN_USERNAME", "admin")
    DEMO_ADMIN_EMAIL = os.getenv("DEMO_ADMIN_EMAIL", "admin@ksp.local")
    DEMO_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "ChangeMe123!")
    DEMO_ADMIN_NAME = os.getenv("DEMO_ADMIN_NAME", "Platform Administrator")


class DevelopmentConfig(Config):
    """Safe-to-bootstrap local development configuration."""

    DEBUG = _as_bool(os.getenv("FLASK_DEBUG"), True)
    AUTO_CREATE_DB = _as_bool(os.getenv("AUTO_CREATE_DB"), True)
    SEED_DEMO_ADMIN = _as_bool(os.getenv("SEED_DEMO_ADMIN"), True)


class TestingConfig(Config):
    """Configuration intended for automated tests."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")
    AUTO_CREATE_DB = True
    SEED_DEMO_ADMIN = False


class ProductionConfig(Config):
    """Production defaults keep schema creation and demo accounts opt-in."""

    APP_ENV = "production"
    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SESSION_COOKIE_SECURE"), True)


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
    "prod": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a named configuration class with development as the default."""
    return CONFIG_BY_NAME.get((name or "development").lower(), DevelopmentConfig)
