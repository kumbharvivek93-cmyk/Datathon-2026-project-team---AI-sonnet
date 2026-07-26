"""Business logic for dashboard metrics and practical intelligence signals."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import mean
from typing import Any, Iterable, Mapping

from app.api.serializers import (
    as_bool,
    as_float,
    fetch_records,
    normalise,
    parse_date,
    serialize_crime,
    serialize_link,
    serialize_suspect,
    value_of,
)


VIOLENT_CRIME_TERMS = {
    "murder",
    "homicide",
    "rape",
    "assault",
    "kidnapping",
    "robbery",
    "dacoity",
    "attempt to murder",
}
SOLVED_STATUSES = {"solved", "closed", "charge sheet filed", "chargesheet filed", "disposed"}


def _label(value: Any, fallback: str = "Unspecified") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _counter_rows(counter: Counter[str], limit: int = 12, key: str = "label") -> list[dict[str, Any]]:
    return [{key: label, "count": count} for label, count in counter.most_common(limit)]


def _date_for(crime: Any) -> date | None:
    return parse_date(value_of(crime, "date", "incident_date", "occurred_on"))


def _hour_for(crime: Any) -> int | None:
    raw = value_of(crime, "time", "incident_time", "occurred_at")
    if raw is None:
        return None
    if hasattr(raw, "hour"):
        try:
            return int(raw.hour)
        except (TypeError, ValueError):
            return None
    text = str(raw).strip()
    try:
        return int(text.split(":", 1)[0]) % 24
    except (TypeError, ValueError):
        return None


def detect_crime_anomalies(records: Iterable[Any] | None = None, limit: int = 100) -> dict[str, Any]:
    """Identify unusual combinations of date, place, category, and time.

    IsolationForest is used when installed and enough observations exist.  A
    deterministic rarity heuristic remains available for lightweight/dev
    installs, so an analytics endpoint never silently disappears.
    """
    crimes = list(records if records is not None else fetch_records("CrimeIncident"))
    if not crimes:
        return {"method": "no_data", "anomalies": [], "anomaly_count": 0}

    district_labels = sorted({_label(value_of(record, "district")) for record in crimes})
    category_labels = sorted(
        {_label(value_of(record, "crime_type", "category", "offence_type")) for record in crimes}
    )
    districts = {label: index for index, label in enumerate(district_labels)}
    categories = {label: index for index, label in enumerate(category_labels)}
    dates = [_date_for(record) for record in crimes]
    known_dates = [item for item in dates if item]
    baseline = min(known_dates).toordinal() if known_dates else date.today().toordinal()
    features: list[list[float]] = []
    for crime, crime_date in zip(crimes, dates):
        features.append(
            [
                float((crime_date.toordinal() if crime_date else baseline) - baseline),
                as_float(value_of(crime, "latitude", "lat"), 0.0) or 0.0,
                as_float(value_of(crime, "longitude", "lng", "lon"), 0.0) or 0.0,
                float(_hour_for(crime) or 12),
                float(districts[_label(value_of(crime, "district"))]),
                float(categories[_label(value_of(crime, "crime_type", "category", "offence_type"))]),
            ]
        )

    anomalies: list[dict[str, Any]] = []
    method = "rarity_heuristic"
    if len(crimes) >= 12:
        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                contamination="auto", random_state=42, n_estimators=150
            )
            labels = model.fit_predict(features)
            scores = model.decision_function(features)
            method = "isolation_forest"
            for crime, label, score in zip(crimes, labels, scores):
                if int(label) == -1:
                    payload = serialize_crime(crime)
                    payload.update(
                        {
                            "anomaly_score": round(float(-score), 4),
                            "reason": "Unusual combination of time, place, and crime profile",
                        }
                    )
                    anomalies.append(payload)
        except (ImportError, ValueError, TypeError):
            # The fallback below is deliberately conservative and explainable.
            method = "rarity_heuristic"

    if method == "rarity_heuristic":
        category_count = Counter(
            _label(value_of(item, "crime_type", "category", "offence_type")) for item in crimes
        )
        district_count = Counter(_label(value_of(item, "district")) for item in crimes)
        for crime in crimes:
            category = _label(value_of(crime, "crime_type", "category", "offence_type"))
            district = _label(value_of(crime, "district"))
            hour = _hour_for(crime)
            rare = category_count[category] <= max(1, len(crimes) // 20)
            isolated = district_count[district] <= max(1, len(crimes) // 25)
            unusual_hour = hour is not None and (hour <= 3 or hour >= 23)
            if rare or (isolated and unusual_hour):
                payload = serialize_crime(crime)
                payload.update(
                    {
                        "anomaly_score": round(
                            (1 / max(category_count[category], 1))
                            + (0.3 if unusual_hour else 0),
                            4,
                        ),
                        "reason": "Rare category/location pattern" if rare else "Sparse late-night pattern",
                    }
                )
                anomalies.append(payload)

    anomalies.sort(key=lambda item: item.get("anomaly_score", 0), reverse=True)
    return {
        "method": method,
        "anomalies": anomalies[: max(1, min(limit, 500))],
        "anomaly_count": len(anomalies),
    }


def discover_patterns(
    records: Iterable[Any] | None = None, links: Iterable[Any] | None = None
) -> dict[str, Any]:
    """Return explainable frequency patterns useful to analysts and reports."""
    crimes = list(records if records is not None else fetch_records("CrimeIncident"))
    relation_rows = list(links if links is not None else _safe_fetch("CrimeLink"))
    mo = Counter(_label(value_of(item, "modus_operandi", "mo")) for item in crimes)
    locations = Counter(
        f"{_label(value_of(item, 'district'))} · {_label(value_of(item, 'police_station', 'station'))}"
        for item in crimes
    )
    types = Counter(
        _label(value_of(item, "crime_type", "category", "offence_type")) for item in crimes
    )
    hours = Counter(str(_hour_for(item)).zfill(2) + ":00" for item in crimes if _hour_for(item) is not None)
    weekdays = Counter(
        _date_for(item).strftime("%A") for item in crimes if _date_for(item) is not None
    )
    months = Counter(
        _date_for(item).strftime("%Y-%m") for item in crimes if _date_for(item) is not None
    )
    victim_count = Counter(
        str(link["victim_id"])
        for link in (serialize_link(item) for item in relation_rows)
        if link.get("victim_id") is not None
    )
    suspect_count = Counter(
        str(link["suspect_id"])
        for link in (serialize_link(item) for item in relation_rows)
        if link.get("suspect_id") is not None
    )
    return {
        "record_count": len(crimes),
        "common_modus_operandi": _counter_rows(mo),
        "frequent_locations": _counter_rows(locations),
        "crime_types": _counter_rows(types),
        "time_of_day": _counter_rows(hours, key="hour"),
        "day_of_week": _counter_rows(weekdays, key="day"),
        "seasonality": _counter_rows(months, key="month"),
        "repeat_victims": [
            {"victim_id": victim_id, "incidents": count}
            for victim_id, count in victim_count.most_common(10)
            if count > 1
        ],
        "repeat_offenders": [
            {"suspect_id": suspect_id, "incidents": count}
            for suspect_id, count in suspect_count.most_common(10)
            if count > 1
        ],
    }


def _safe_fetch(name: str) -> list[Any]:
    try:
        return fetch_records(name)
    except Exception:
        return []


def score_suspects(
    suspects: Iterable[Any] | None = None,
    links: Iterable[Any] | None = None,
    crimes: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Calculate transparent 0–100 risk scores without mutating source data."""
    suspect_rows = list(suspects if suspects is not None else _safe_fetch("Suspect"))
    link_rows = [serialize_link(item) for item in (links if links is not None else _safe_fetch("CrimeLink"))]
    crime_rows = {
        str(value_of(item, "id")): item
        for item in (crimes if crimes is not None else _safe_fetch("CrimeIncident"))
        if value_of(item, "id") is not None
    }
    linked_crimes: dict[str, list[Any]] = defaultdict(list)
    for link in link_rows:
        suspect_id, crime_id = link.get("suspect_id"), link.get("crime_id")
        if suspect_id is not None and crime_id is not None and str(crime_id) in crime_rows:
            linked_crimes[str(suspect_id)].append(crime_rows[str(crime_id)])

    today = date.today()
    results: list[dict[str, Any]] = []
    for suspect in suspect_rows:
        data = serialize_suspect(suspect)
        key = str(data.get("id") if data.get("id") is not None else data.get("person_id"))
        related = linked_crimes.get(key, [])
        repeat_points = min(len(related) * 8, 32)
        violent_points = min(
            sum(
                7
                for crime in related
                if any(
                    term in normalise(value_of(crime, "crime_type", "category", "offence_type"))
                    for term in VIOLENT_CRIME_TERMS
                )
            ),
            25,
        )
        gang_points = 15 if _label(data.get("gang_name"), "") else 0
        repeat_flag_points = 12 if as_bool(data.get("repeat_offender")) else 0
        recent_points = 0
        for crime in related:
            incident_date = _date_for(crime)
            if incident_date and (today - incident_date).days <= 180:
                recent_points += 4
        wanted_level = normalise(data.get("wanted_level"))
        wanted_points = 12 if wanted_level in {"high", "most wanted", "critical"} else 6 if wanted_level else 0
        calculated = min(100, round(repeat_points + violent_points + gang_points + repeat_flag_points + min(recent_points, 16) + wanted_points))
        stored = as_float(data.get("risk_score"))
        data.update(
            {
                "risk_score": calculated if stored is None else round(max(stored, calculated), 1),
                "linked_crime_count": len(related),
                "risk_factors": {
                    "repeat_offences": repeat_points,
                    "violent_offences": violent_points,
                    "gang_association": gang_points,
                    "recent_activity": min(recent_points, 16),
                    "wanted_level": wanted_points,
                },
            }
        )
        results.append(data)
    return sorted(results, key=lambda item: item.get("risk_score") or 0, reverse=True)


def dashboard_snapshot(records: Iterable[Any] | None = None) -> dict[str, Any]:
    """Build dashboard data in a single serializable payload."""
    crimes = list(records if records is not None else fetch_records("CrimeIncident"))
    suspects = _safe_fetch("Suspect")
    statuses = Counter(normalise(value_of(item, "status", default="Pending")) for item in crimes)
    district_counter = Counter(_label(value_of(item, "district")) for item in crimes)
    type_counter = Counter(
        _label(value_of(item, "crime_type", "category", "offence_type")) for item in crimes
    )
    station_counter = Counter(_label(value_of(item, "police_station", "station")) for item in crimes)
    monthly_counter = Counter(
        _date_for(item).strftime("%Y-%m") for item in crimes if _date_for(item) is not None
    )
    solved = sum(count for status, count in statuses.items() if status in SOLVED_STATUSES)
    pending = max(len(crimes) - solved, 0)
    repeat_offenders = sum(
        1 for suspect in suspects if as_bool(value_of(suspect, "repeat_offender"))
    )
    max_district_count = max(district_counter.values(), default=0)
    district_rows = [
        {
            "district": district,
            "count": count,
            "heat_index": round((count / max_district_count) * 100, 1) if max_district_count else 0,
        }
        for district, count in district_counter.most_common(15)
    ]
    anomalies = detect_crime_anomalies(crimes, limit=8)
    patterns = discover_patterns(crimes)
    return {
        "summary": {
            "total_crimes": len(crimes),
            "solved_cases": solved,
            "pending_cases": pending,
            "repeat_offenders": repeat_offenders,
            "most_active_district": district_counter.most_common(1)[0][0] if district_counter else None,
            "crime_heat_index": round((solved / len(crimes)) * 100, 1) if crimes else 0,
        },
        "monthly_trend": [
            {"month": month, "count": count} for month, count in sorted(monthly_counter.items())
        ],
        "crime_categories": _counter_rows(type_counter, key="crime_type"),
        "district_comparison": district_rows,
        "top_crime_types": _counter_rows(type_counter, limit=8, key="crime_type"),
        "top_police_stations": _counter_rows(station_counter, limit=8, key="police_station"),
        "anomalies": anomalies,
        "patterns": patterns,
    }


def socioeconomic_snapshot(records: Iterable[Any] | None = None) -> dict[str, Any]:
    """Join available socioeconomic rows to incident counts for visual overlays."""
    crimes = list(records if records is not None else fetch_records("CrimeIncident"))
    socioeconomic = _safe_fetch("SocioEconomicData")
    crime_by_district = Counter(_label(value_of(item, "district")) for item in crimes)
    rows: list[dict[str, Any]] = []
    for item in socioeconomic:
        district = _label(value_of(item, "district"))
        population = as_float(value_of(item, "population"))
        count = crime_by_district.get(district, 0)
        rows.append(
            {
                "district": district,
                "crime_count": count,
                "population": population,
                "crime_density_per_100k": round((count / population) * 100000, 2) if population else None,
                "literacy": as_float(value_of(item, "literacy", "literacy_rate")),
                "urbanization": as_float(value_of(item, "urbanization", "urbanization_rate")),
                "poverty_index": as_float(value_of(item, "poverty_index")),
                "unemployment": as_float(value_of(item, "unemployment", "unemployment_rate")),
                "education_index": as_float(value_of(item, "education_index")),
            }
        )
    if not rows:
        rows = [
            {"district": district, "crime_count": count, "population": None, "crime_density_per_100k": None}
            for district, count in crime_by_district.most_common()
        ]
    return {"districts": rows, "record_count": len(rows)}
