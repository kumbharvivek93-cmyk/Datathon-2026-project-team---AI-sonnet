"""Read-only REST endpoints for crimes, suspects, and dashboard summaries."""

from __future__ import annotations

from datetime import date
from typing import Any

from flask import Blueprint, jsonify, request

from app.analytics.services import dashboard_snapshot, score_suspects
from .serializers import (
    ModelUnavailable,
    as_bool,
    as_int,
    fetch_records,
    filter_crimes,
    normalise,
    paginate,
    parse_date,
    serialize_crime,
    serialize_suspect,
    value_of,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")


def _unavailable(exc: Exception, empty: Any) -> tuple:
    return jsonify({"error": str(exc), "data": empty}), 503


def _sort_crimes(records: list[Any]) -> list[Any]:
    return sorted(
        records,
        key=lambda item: parse_date(value_of(item, "date", "incident_date", "occurred_on")) or date.min,
        reverse=True,
    )


@api_bp.get("/crimes")
def crimes() -> tuple:
    """List crime incidents with bounded pagination and common investigation filters."""
    try:
        filters = request.args.to_dict(flat=True)
        records = _sort_crimes(filter_crimes(fetch_records("CrimeIncident"), filters))
        items, pagination = paginate(
            records,
            as_int(filters.get("page"), 1),
            as_int(filters.get("per_page") or filters.get("limit"), 50),
        )
        return jsonify(
            {
                "data": [serialize_crime(item) for item in items],
                "pagination": pagination,
                "filters": {
                    key: value
                    for key, value in filters.items()
                    if key not in {"page", "per_page", "limit"} and value not in (None, "")
                },
            }
        ), 200
    except ModelUnavailable as exc:
        return _unavailable(exc, [])


def _filter_suspects(records: list[Any], filters: dict[str, str]) -> list[Any]:
    search = normalise(filters.get("q") or filters.get("search"))
    gang = normalise(filters.get("gang") or filters.get("gang_name"))
    wanted = normalise(filters.get("wanted_level"))
    wants_repeat = filters.get("repeat_offender")
    filtered: list[Any] = []
    for suspect in records:
        data = serialize_suspect(suspect)
        if gang and normalise(data.get("gang_name")) != gang:
            continue
        if wanted and normalise(data.get("wanted_level")) != wanted:
            continue
        if wants_repeat is not None and data.get("repeat_offender") != as_bool(wants_repeat):
            continue
        if search:
            text = " ".join(
                normalise(data.get(field)) for field in ("name", "gang_name", "phone", "wanted_level")
            )
            if search not in text:
                continue
        filtered.append(suspect)
    return filtered


@api_bp.get("/suspects")
def suspects() -> tuple:
    """List suspect profiles, enriching each with a calculated risk score."""
    try:
        filters = request.args.to_dict(flat=True)
        raw_records = _filter_suspects(fetch_records("Suspect"), filters)
        scores = score_suspects(suspects=raw_records)
        items, pagination = paginate(
            scores,
            as_int(filters.get("page"), 1),
            as_int(filters.get("per_page") or filters.get("limit"), 50),
        )
        return jsonify({"data": items, "pagination": pagination}), 200
    except ModelUnavailable as exc:
        return _unavailable(exc, [])


@api_bp.get("/dashboard")
def dashboard() -> tuple:
    """Return summary cards, chart series, patterns, and explainable anomalies."""
    try:
        filters = request.args.to_dict(flat=True)
        records = filter_crimes(fetch_records("CrimeIncident"), filters)
        payload = dashboard_snapshot(records)
        payload["filters"] = {
            key: value for key, value in filters.items() if value not in (None, "")
        }
        return jsonify(payload), 200
    except ModelUnavailable as exc:
        return _unavailable(exc, {})
