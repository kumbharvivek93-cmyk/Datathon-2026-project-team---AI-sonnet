"""Additional analysis endpoints consumed by dashboards and internal tools."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.api.serializers import ModelUnavailable, as_int, fetch_records, filter_crimes
from .services import detect_crime_anomalies, discover_patterns, socioeconomic_snapshot


analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.get("/analytics")
@login_required
def analytics_page() -> str:
    return render_template("analytics/index.html")


@analytics_bp.get("/api/analytics/patterns")
def patterns() -> tuple:
    try:
        crimes = filter_crimes(fetch_records("CrimeIncident"), request.args)
        return jsonify(discover_patterns(crimes)), 200
    except ModelUnavailable as exc:
        return jsonify({"error": str(exc), "data": {}}), 503


@analytics_bp.get("/api/anomalies")
def anomalies() -> tuple:
    try:
        crimes = filter_crimes(fetch_records("CrimeIncident"), request.args)
        return jsonify(detect_crime_anomalies(crimes, as_int(request.args.get("limit"), 100) or 100)), 200
    except ModelUnavailable as exc:
        return jsonify({"error": str(exc), "data": []}), 503


@analytics_bp.get("/api/analytics/socioeconomic")
def socioeconomic() -> tuple:
    try:
        crimes = filter_crimes(fetch_records("CrimeIncident"), request.args)
        return jsonify(socioeconomic_snapshot(crimes)), 200
    except ModelUnavailable as exc:
        return jsonify({"error": str(exc), "data": {}}), 503
