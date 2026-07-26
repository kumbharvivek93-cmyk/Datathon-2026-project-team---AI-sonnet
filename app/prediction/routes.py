"""Explainable baseline prediction endpoints for operational planning."""

from collections import Counter
from datetime import date

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.models.core import CrimeIncident

prediction_bp = Blueprint("prediction", __name__)


def predict(district: str, crime_type: str, month: int):
    rows = CrimeIncident.query.all()
    matched = [r for r in rows if (not district or r.district == district) and (not crime_type or r.crime_type == crime_type)]
    monthly = Counter((r.date.year, r.date.month) for r in matched)
    average = round(sum(monthly.values()) / max(len(monthly), 1), 1)
    expected = max(0, round(average * (1.12 if month in {10, 11, 12} else 1)))
    return {"district": district or "All districts", "crime_type": crime_type or "All categories", "month": month, "expected_crime_count": expected, "risk_level": "High" if expected >= 8 else "Medium" if expected >= 4 else "Low", "method": "Historical monthly baseline (decision support, not a certainty)."}


@prediction_bp.get("/prediction")
@login_required
def index():
    rows = CrimeIncident.query.all()
    return render_template("prediction/index.html", page_title="AI Prediction", districts=sorted({r.district for r in rows}), crime_types=sorted({r.crime_type for r in rows}))


@prediction_bp.get("/api/predictions")
def api_prediction():
    return jsonify(predict(request.args.get("district", ""), request.args.get("crime_type", ""), request.args.get("month", date.today().month, type=int)))


@prediction_bp.get("/api/hotspots")
def hotspots():
    points = [r for r in CrimeIncident.query.all() if r.latitude is not None and r.longitude is not None]
    counts = Counter((round(r.latitude, 2), round(r.longitude, 2), r.district) for r in points)
    data = [{"latitude": lat, "longitude": lng, "district": district, "incident_count": count} for (lat, lng, district), count in counts.most_common(30)]
    return jsonify({"data": data, "method": "Spatial grid density hotspot detection"})
