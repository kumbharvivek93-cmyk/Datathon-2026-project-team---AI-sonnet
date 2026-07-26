"""Small, dependency-light helpers shared by API and analytics services.

The application deliberately keeps model imports lazy.  This makes the API
blueprints importable while Flask is being configured and avoids a circular
dependency between the app factory, SQLAlchemy models, and route modules.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from importlib import import_module
from typing import Any
from uuid import UUID


class ModelUnavailable(RuntimeError):
    """Raised when a requested model is unavailable in the active build."""


def get_model(name: str) -> type:
    """Return a model from ``app.models.core`` only when it is needed."""
    try:
        module = import_module("app.models.core")
        model = getattr(module, name)
    except (ImportError, AttributeError) as exc:
        raise ModelUnavailable(f"The {name} model is not available.") from exc
    return model


def fetch_records(model_name: str) -> list[Any]:
    """Fetch model rows while supporting the normal Flask-SQLAlchemy query API."""
    model = get_model(model_name)
    query = getattr(model, "query", None)
    if query is None:
        raise ModelUnavailable(f"The {model_name} model does not expose a query API.")
    try:
        return list(query.all())
    except Exception as exc:  # SQLAlchemy reports useful details in Flask logs.
        raise ModelUnavailable(f"Unable to load {model_name} records.") from exc


def value_of(item: Any, *names: str, default: Any = None) -> Any:
    """Read the first existing attribute/key without leaking ORM internals."""
    for name in names:
        if isinstance(item, Mapping) and name in item:
            return item[name]
        try:
            value = getattr(item, name)
        except (AttributeError, RuntimeError):
            continue
        if value is not None:
            return value
    return default


def iso_value(value: Any) -> Any:
    """Convert common ORM values into JSON-safe scalar values."""
    if value is None:
        return None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, Enum):
        return iso_value(value.value)
    return value


def json_value(value: Any, depth: int = 0) -> Any:
    """Make a value safe for ``jsonify`` without traversing ORM relationships."""
    if depth > 3:
        return str(value)
    scalar = iso_value(value)
    if scalar is None or isinstance(scalar, (str, int, float, bool)):
        return scalar
    if isinstance(scalar, Mapping):
        return {str(key): json_value(item, depth + 1) for key, item in scalar.items()}
    if isinstance(scalar, Iterable) and not isinstance(scalar, (str, bytes, bytearray)):
        return [json_value(item, depth + 1) for item in scalar]
    return str(scalar)


def as_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "on"}


def parse_date(value: Any) -> date | None:
    """Accept native dates and the most common ISO-style date strings."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalise(value: Any) -> str:
    return "" if value is None else str(value).strip().casefold()


def serialize_person(person: Any | None) -> dict[str, Any] | None:
    if person is None:
        return None
    return {
        "id": value_of(person, "id"),
        "name": value_of(person, "name", "full_name", default="Unknown"),
        "age": as_int(value_of(person, "age")),
        "gender": value_of(person, "gender"),
        "phone": value_of(person, "phone", "phone_number"),
    }


def serialize_crime(crime: Any) -> dict[str, Any]:
    latitude = as_float(value_of(crime, "latitude", "lat"))
    longitude = as_float(value_of(crime, "longitude", "lng", "lon"))
    return {
        "id": value_of(crime, "id"),
        "crime_number": value_of(crime, "crime_number", "case_number", "fir_number"),
        "date": iso_value(value_of(crime, "date", "incident_date", "occurred_on")),
        "time": iso_value(value_of(crime, "time", "incident_time", "occurred_at")),
        "district": value_of(crime, "district"),
        "police_station": value_of(crime, "police_station", "station"),
        "latitude": latitude,
        "longitude": longitude,
        "crime_type": value_of(crime, "crime_type", "category", "offence_type"),
        "ipc_sections": value_of(crime, "ipc_sections", "ipc_section"),
        "status": value_of(crime, "status", default="Pending"),
        "modus_operandi": value_of(crime, "modus_operandi", "mo"),
        "description": value_of(crime, "description", "details"),
        "created_at": iso_value(value_of(crime, "created_at")),
        "updated_at": iso_value(value_of(crime, "updated_at")),
    }


def serialize_suspect(suspect: Any) -> dict[str, Any]:
    person = value_of(suspect, "person")
    person_data = serialize_person(person)
    return {
        "id": value_of(suspect, "id", "person_id"),
        "person_id": value_of(suspect, "person_id", default=value_of(person, "id")),
        "name": value_of(suspect, "name", default=(person_data or {}).get("name", "Unknown")),
        "age": as_int(value_of(suspect, "age", default=(person_data or {}).get("age"))),
        "gender": value_of(suspect, "gender", default=(person_data or {}).get("gender")),
        "phone": value_of(suspect, "phone", default=(person_data or {}).get("phone")),
        "gang_name": value_of(suspect, "gang_name", "gang"),
        "risk_score": as_float(value_of(suspect, "risk_score")),
        "repeat_offender": as_bool(value_of(suspect, "repeat_offender")),
        "wanted_level": value_of(suspect, "wanted_level"),
        "person": person_data,
    }


def serialize_victim(victim: Any) -> dict[str, Any]:
    person = value_of(victim, "person")
    person_data = serialize_person(person)
    return {
        "id": value_of(victim, "id", "person_id"),
        "person_id": value_of(victim, "person_id", default=value_of(person, "id")),
        "name": value_of(victim, "name", default=(person_data or {}).get("name", "Unknown")),
        "person": person_data,
    }


def serialize_link(link: Any) -> dict[str, Any]:
    return {
        "id": value_of(link, "id"),
        "crime_id": value_of(link, "crime_id", default=value_of(value_of(link, "crime"), "id")),
        "suspect_id": value_of(link, "suspect_id", default=value_of(value_of(link, "suspect"), "id", "person_id")),
        "victim_id": value_of(link, "victim_id", default=value_of(value_of(link, "victim"), "id", "person_id")),
        "relationship": value_of(link, "relationship", "relationship_type", default="Associated"),
    }


def filter_crimes(records: Iterable[Any], filters: Mapping[str, Any]) -> list[Any]:
    """Apply API filters in Python so model field naming can evolve safely."""
    district = normalise(filters.get("district"))
    station = normalise(filters.get("police_station"))
    crime_type = normalise(filters.get("crime_type"))
    status = normalise(filters.get("status"))
    search = normalise(filters.get("q") or filters.get("search"))
    start = parse_date(filters.get("start_date") or filters.get("date_from"))
    end = parse_date(filters.get("end_date") or filters.get("date_to"))
    matched: list[Any] = []
    for record in records:
        record_date = parse_date(value_of(record, "date", "incident_date", "occurred_on"))
        if start and (record_date is None or record_date < start):
            continue
        if end and (record_date is None or record_date > end):
            continue
        if district and normalise(value_of(record, "district")) != district:
            continue
        if station and normalise(value_of(record, "police_station", "station")) != station:
            continue
        if crime_type and normalise(value_of(record, "crime_type", "category", "offence_type")) != crime_type:
            continue
        if status and normalise(value_of(record, "status")) != status:
            continue
        if search:
            haystack = " ".join(
                normalise(value_of(record, field))
                for field in (
                    "crime_number",
                    "case_number",
                    "fir_number",
                    "district",
                    "police_station",
                    "crime_type",
                    "description",
                    "modus_operandi",
                )
            )
            if search not in haystack:
                continue
        matched.append(record)
    return matched


def paginate(items: list[Any], page: int | None, per_page: int | None) -> tuple[list[Any], dict[str, int]]:
    current_page = max(page or 1, 1)
    size = min(max(per_page or 50, 1), 200)
    total = len(items)
    start = (current_page - 1) * size
    return items[start : start + size], {
        "page": current_page,
        "per_page": size,
        "total": total,
        "pages": max((total + size - 1) // size, 1),
    }
