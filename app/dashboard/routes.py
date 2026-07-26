"""Server-rendered investigative views and contextual search."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from io import BytesIO
from math import ceil
from typing import Any

from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.dashboard import dashboard_bp
from app.extensions import db
from app.auth.decorators import roles_required
from app.models.core import CrimeIncident, CrimeLink, FIRDetail, Person, Role, SocioEconomicData, Suspect


def _count(statement: Any) -> int:
    """Return an integer for a lightweight SQLAlchemy count statement."""
    return int(db.session.scalar(statement) or 0)


def _query_count(query: Any) -> int:
    """Keep legacy and SQLAlchemy 2 query paths concise in route code."""
    return int(query.count())


def _date_value(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _chart_payload(incidents: list[CrimeIncident]) -> dict[str, list[Any]]:
    """Calculate presentation-sized aggregates without DB-specific date SQL."""
    month_counter: Counter[str] = Counter()
    district_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    for incident in incidents:
        incident_date = _date_value(incident.date)
        if incident_date:
            month_counter[incident_date.strftime("%b %Y")] += 1
        district_counter[incident.district] += 1
        type_counter[incident.crime_type] += 1

    month_items = sorted(
        month_counter.items(),
        key=lambda item: datetime.strptime(item[0], "%b %Y"),
    )[-12:]
    district_items = district_counter.most_common(8)
    type_items = type_counter.most_common(8)
    return {
        "monthly_labels": [item[0] for item in month_items],
        "monthly_values": [item[1] for item in month_items],
        "district_labels": [item[0] for item in district_items],
        "district_values": [item[1] for item in district_items],
        "type_labels": [item[0] for item in type_items],
        "type_values": [item[1] for item in type_items],
    }


def _metrics(incidents: list[CrimeIncident]) -> dict[str, Any]:
    total = len(incidents)
    solved = sum(incident.status == "Solved" for incident in incidents)
    pending = sum(incident.status in {"Open", "Under Investigation"} for incident in incidents)
    district_counter = Counter(incident.district for incident in incidents)
    repeat_offenders = _query_count(Suspect.query.filter_by(repeat_offender=True))
    # The heat index favours unresolved, high-volume case loads; it is a
    # decision-support signal rather than a measure of public safety.
    heat_index = round(((pending * 1.35 + total * 0.25) / max(total, 1)) * 100, 1)
    return {
        "total_crimes": total,
        "solved_cases": solved,
        "pending_cases": pending,
        "repeat_offenders": repeat_offenders,
        "most_active_district": district_counter.most_common(1)[0][0] if district_counter else "—",
        "crime_heat_index": min(100, heat_index),
        "clearance_rate": round((solved / total) * 100, 1) if total else 0,
    }


def _map_records(incidents: list[CrimeIncident], limit: int = 450) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for incident in incidents[-limit:]:
        if incident.latitude is None or incident.longitude is None:
            continue
        records.append(
            {
                "id": incident.id,
                "lat": float(incident.latitude),
                "lng": float(incident.longitude),
                "crime_number": incident.crime_number,
                "crime_type": incident.crime_type,
                "district": incident.district,
                "station": incident.police_station,
                "status": incident.status,
                "date": str(incident.date),
            }
        )
    return records


@dashboard_bp.route("/")
@login_required
def index():
    incidents = CrimeIncident.query.order_by(CrimeIncident.date.asc()).all()
    charts = _chart_payload(incidents)
    return render_template(
        "dashboard/index.html",
        page_title="Command Dashboard",
        metrics=_metrics(incidents),
        recent_crimes=list(reversed(incidents[-8:])),
        chart_data=charts,
        map_records=_map_records(incidents),
        districts=sorted({incident.district for incident in incidents}),
        crime_types=sorted({incident.crime_type for incident in incidents}),
    )


@dashboard_bp.route("/crimes")
@login_required
def crimes():
    query = CrimeIncident.query
    filters = {
        "district": request.args.get("district", "").strip(),
        "crime_type": request.args.get("crime_type", "").strip(),
        "status": request.args.get("status", "").strip(),
        "station": request.args.get("station", "").strip(),
        "start_date": request.args.get("start_date", "").strip(),
        "end_date": request.args.get("end_date", "").strip(),
    }
    if filters["district"]:
        query = query.filter_by(district=filters["district"])
    if filters["crime_type"]:
        query = query.filter_by(crime_type=filters["crime_type"])
    if filters["status"]:
        query = query.filter_by(status=filters["status"])
    if filters["station"]:
        query = query.filter_by(police_station=filters["station"])
    start_date = _date_value(filters["start_date"])
    end_date = _date_value(filters["end_date"])
    if start_date:
        query = query.filter(CrimeIncident.date >= start_date)
    if end_date:
        query = query.filter(CrimeIncident.date <= end_date)

    page = max(1, request.args.get("page", 1, type=int))
    per_page = 25
    pagination = query.order_by(CrimeIncident.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    all_incidents = CrimeIncident.query.all()
    return render_template(
        "crimes/list.html",
        page_title="Crime Records",
        incidents=pagination.items,
        crimes=pagination.items,
        pagination=pagination,
        filters=filters,
        districts=sorted({incident.district for incident in all_incidents}),
        crime_types=sorted({incident.crime_type for incident in all_incidents}),
        stations=sorted({incident.police_station for incident in all_incidents}),
        statuses=sorted({incident.status for incident in all_incidents}),
    )


@dashboard_bp.route("/crimes/<int:crime_id>")
@login_required
def crime_detail(crime_id: int):
    incident = db.get_or_404(CrimeIncident, crime_id)
    links = CrimeLink.query.filter_by(crime_id=crime_id).all()
    return render_template(
        "crimes/detail.html",
        page_title=incident.crime_number,
        crime=incident,
        incident=incident,
        links=links,
    )


def _form_date(name: str, required: bool = False) -> date | None:
    value = request.form.get(name, "").strip()
    if not value:
        if required:
            raise ValueError(f"{name.replace('_', ' ').title()} is required.")
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _form_time(name: str) -> datetime.time | None:
    value = request.form.get(name, "").strip()
    return datetime.strptime(value, "%H:%M").time() if value else None


@dashboard_bp.route("/fir/new", methods=["GET", "POST"])
@login_required
@roles_required(Role.ADMIN, Role.OFFICER)
def file_fir():
    """Capture an FIR and create its linked crime incident atomically."""
    if request.method == "POST":
        try:
            required = ("informant_name", "informant_address", "district", "police_station", "crime_type", "place_of_occurrence", "complaint_text", "recording_officer")
            missing = [field.replace("_", " ") for field in required if not request.form.get(field, "").strip()]
            if missing:
                raise ValueError("Please complete: " + ", ".join(missing) + ".")
            occurred_date = _form_date("occurred_date", required=True)
            report_date = _form_date("report_date", required=True)
            sequence = CrimeIncident.query.count() + 1
            incident = CrimeIncident(
                crime_number=f"FIR-{report_date:%Y}-{sequence:06d}",
                date=occurred_date,
                time=_form_time("occurred_time"),
                district=request.form["district"].strip(),
                police_station=request.form["police_station"].strip(),
                crime_type=request.form["crime_type"].strip(),
                ipc_sections=request.form.get("ipc_sections", "").strip() or None,
                status="Open",
                modus_operandi=request.form.get("modus_operandi", "").strip() or None,
                description=request.form.get("complaint_text", "").strip(),
            )
            detail = FIRDetail(
                incident=incident,
                informant_name=request.form["informant_name"].strip(),
                informant_address=request.form["informant_address"].strip(),
                informant_phone=request.form.get("informant_phone", "").strip() or None,
                informant_age=request.form.get("informant_age", type=int),
                informant_gender=request.form.get("informant_gender", "").strip() or None,
                report_date=report_date,
                report_time=_form_time("report_time"),
                occurrence_end_date=_form_date("occurrence_end_date"),
                occurrence_end_time=_form_time("occurrence_end_time"),
                place_of_occurrence=request.form["place_of_occurrence"].strip(),
                distance_direction_from_station=request.form.get("distance_direction_from_station", "").strip() or None,
                complaint_text=request.form["complaint_text"].strip(),
                delay_reason=request.form.get("delay_reason", "").strip() or None,
                accused_details=request.form.get("accused_details", "").strip() or None,
                property_details=request.form.get("property_details", "").strip() or None,
                injuries_or_death=request.form.get("injuries_or_death", "").strip() or None,
                action_taken=request.form.get("action_taken", "").strip() or None,
                recording_officer=request.form["recording_officer"].strip(),
                officer_designation=request.form.get("officer_designation", "").strip() or None,
            )
            db.session.add_all((incident, detail))
            db.session.commit()
            flash(f"FIR {incident.crime_number} has been registered.", "success")
            return redirect(url_for("dashboard.crime_detail", crime_id=incident.id))
        except (ValueError, TypeError) as error:
            flash(str(error), "danger")
        except Exception:
            db.session.rollback()
            flash("The FIR could not be saved. Please review the fields and try again.", "danger")

    return render_template(
        "fir/new.html", page_title="File FIR",
        today=date.today().isoformat(),
        officer_name=current_user.full_name or current_user.username,
    )


def _natural_language_search(query_text: str) -> tuple[list[CrimeIncident], dict[str, str]]:
    """Interpret a small, transparent subset of investigation-style queries.

    It intentionally uses deterministic keyword extraction instead of sending
    operational data to an external model.  The matching rules are displayed in
    the UI so an analyst can verify the result.
    """
    text = query_text.casefold()
    query = CrimeIncident.query
    applied: dict[str, str] = {}
    districts = {row.district for row in CrimeIncident.query.with_entities(CrimeIncident.district).all()}
    for district in districts:
        if district.casefold() in text:
            query = query.filter_by(district=district)
            applied["District"] = district
            break
    crime_types = {row.crime_type for row in CrimeIncident.query.with_entities(CrimeIncident.crime_type).all()}
    for crime_type in crime_types:
        if crime_type.casefold() in text:
            query = query.filter_by(crime_type=crime_type)
            applied["Crime type"] = crime_type
            break
    if "repeat offender" in text or "repeat-offender" in text:
        suspect_ids = [
            row.id
            for row in Suspect.query.filter_by(repeat_offender=True).with_entities(Suspect.id).all()
        ]
        crime_ids = [
            row.crime_id
            for row in CrimeLink.query.filter(CrimeLink.suspect_id.in_(suspect_ids)).with_entities(CrimeLink.crime_id).all()
        ]
        query = query.filter(CrimeIncident.id.in_(crime_ids or [-1]))
        applied["Subject"] = "Repeat offenders"
    return query.order_by(CrimeIncident.date.desc()).limit(100).all(), applied


@dashboard_bp.route("/search")
@login_required
def search():
    query_text = request.args.get("q", "").strip()
    results: list[CrimeIncident] = []
    applied: dict[str, str] = {}
    if query_text:
        looks_natural = any(
            token in query_text.casefold()
            for token in ("show ", "cases", "involving", "repeat offender", " in ")
        )
        if looks_natural:
            results, applied = _natural_language_search(query_text)
        else:
            search_term = f"%{query_text}%"
            results = (
                CrimeIncident.query.filter(
                    or_(
                        CrimeIncident.crime_number.ilike(search_term),
                        CrimeIncident.district.ilike(search_term),
                        CrimeIncident.police_station.ilike(search_term),
                        CrimeIncident.crime_type.ilike(search_term),
                        CrimeIncident.description.ilike(search_term),
                    )
                )
                .order_by(CrimeIncident.date.desc())
                .limit(100)
                .all()
            )
    suspects = []
    if query_text:
        suspects = (
            Suspect.query.join(Person)
            .filter(Person.name.ilike(f"%{query_text}%"))
            .limit(20)
            .all()
        )
    return render_template(
        "search.html",
        page_title="Intelligence Search",
        query=query_text,
        results=results,
        crimes=results,
        suspects=suspects,
        applied_filters=applied,
    )


@dashboard_bp.route("/offenders/<int:suspect_id>")
@login_required
def offender_profile(suspect_id: int):
    suspect = db.get_or_404(Suspect, suspect_id)
    links = CrimeLink.query.filter_by(suspect_id=suspect_id).all()
    crimes_for_suspect = [db.session.get(CrimeIncident, link.crime_id) for link in links]
    crimes_for_suspect = [crime for crime in crimes_for_suspect if crime]
    connections = (
        Suspect.query.filter(Suspect.gang_name == suspect.gang_name)
        .filter(Suspect.id != suspect.id)
        .limit(12)
        .all()
        if suspect.gang_name
        else []
    )
    return render_template(
        "offenders/profile.html",
        page_title=suspect.person.name if suspect.person else "Offender Profile",
        suspect=suspect,
        crimes=sorted(crimes_for_suspect, key=lambda item: item.date, reverse=True),
        connections=connections,
        links=links,
        districts=sorted({crime.district for crime in crimes_for_suspect}),
    )


@dashboard_bp.route("/sociology")
@login_required
def sociology():
    incidents = CrimeIncident.query.all()
    per_district = Counter(incident.district for incident in incidents)
    rows = SocioEconomicData.query.order_by(SocioEconomicData.district).all()
    district_data = []
    for row in rows:
        total_crimes = per_district[row.district]
        population = row.population or 1
        district_data.append(
            {
                "district": row.district,
                "population": row.population,
                "literacy": row.literacy,
                "urbanization": row.urbanization,
                "poverty_index": row.poverty_index,
                "unemployment": row.unemployment,
                "education_index": row.education_index,
                "crime_count": total_crimes,
                "crime_density": round(total_crimes / population * 100_000, 2),
            }
        )
    return render_template(
        "analytics/sociology.html",
        page_title="Sociological Analysis",
        district_data=district_data,
        correlation_labels=["Crime Density", "Literacy", "Urbanization", "Poverty", "Unemployment"],
    )


def _comparison_records() -> list[CrimeIncident]:
    """Apply the shared comparison filters to incident records."""
    query = CrimeIncident.query
    for field in ("district", "crime_type", "police_station", "status"):
        value = request.args.get(field, "").strip()
        if value:
            query = query.filter(getattr(CrimeIncident, field) == value)
    start, end = _date_value(request.args.get("start_date")), _date_value(request.args.get("end_date"))
    if start:
        query = query.filter(CrimeIncident.date >= start)
    if end:
        query = query.filter(CrimeIncident.date <= end)
    return query.all()


def _comparison_series() -> tuple[list[str], list[float], str, str]:
    records = _comparison_records()
    group_by = request.args.get("group_by", "district")
    metric = request.args.get("metric", "rate")
    if group_by not in {"district", "crime_type", "month"}:
        group_by = "district"
    if metric not in {"count", "rate"}:
        metric = "rate"
    if metric == "rate" and group_by != "district":
        metric = "count"  # Population denominator is available at district level only.
    if group_by == "month":
        counter = Counter(item.date.strftime("%b %Y") for item in records)
        ordered = sorted(counter.items(), key=lambda item: datetime.strptime(item[0], "%b %Y"))
        return [key for key, _ in ordered], [float(value) for _, value in ordered], "Crime incidents", "Monthly crime comparison"
    attribute = "district" if group_by == "district" else "crime_type"
    counter = Counter(getattr(item, attribute) for item in records)
    if metric == "rate":
        populations = {row.district: row.population for row in SocioEconomicData.query.all() if row.population}
        values = [(label, round(count / populations[label] * 100_000, 2)) for label, count in counter.items() if label in populations]
        values.sort(key=lambda item: item[1], reverse=True)
        return [key for key, _ in values], [value for _, value in values], "Incidents per 100,000 residents", "District crime rate comparison"
    values = counter.most_common(20)
    title = "District crime count comparison" if group_by == "district" else "Crime category comparison"
    return [key for key, _ in values], [float(value) for _, value in values], "Recorded incidents", title


@dashboard_bp.get("/comparison")
@login_required
def comparison():
    all_records = CrimeIncident.query.all()
    return render_template(
        "analytics/comparison.html", page_title="Crime Rate Comparison",
        districts=sorted({item.district for item in all_records}),
        crime_types=sorted({item.crime_type for item in all_records}),
        stations=sorted({item.police_station for item in all_records}),
        filters=request.args,
    )


@dashboard_bp.get("/comparison/chart.png")
@login_required
def comparison_chart():
    """Return a PNG chart generated in-memory by Matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    labels, values, y_label, title = _comparison_series()
    figure, axis = plt.subplots(figsize=(11, 5.5), facecolor="#0e2138")
    axis.set_facecolor("#0e2138")
    if labels:
        positions = range(len(labels))
        bars = axis.bar(positions, values, color="#35a7ff", edgecolor="#8bd2ff", linewidth=.6)
        axis.bar_label(bars, labels=[f"{value:g}" for value in values], color="#eaf6ff", fontsize=8, padding=3)
        axis.set_xticks(list(positions), labels, rotation=35, ha="right")
    else:
        axis.text(.5, .5, "No records match the selected filters.", transform=axis.transAxes, ha="center", va="center", color="#b9d5e8", fontsize=12)
    axis.set_title(title, color="#eef8ff", loc="left", fontsize=15, fontweight="bold", pad=15)
    axis.set_ylabel(y_label, color="#b9d5e8")
    axis.tick_params(colors="#b9d5e8")
    for spine in axis.spines.values(): spine.set_color("#31516e")
    axis.grid(axis="y", color="#31516e", alpha=.45, linewidth=.6)
    axis.set_axisbelow(True)
    figure.tight_layout()
    output = BytesIO(); figure.savefig(output, format="png", dpi=150, facecolor=figure.get_facecolor()); plt.close(figure); output.seek(0)
    return send_file(output, mimetype="image/png", max_age=0, download_name="crime-comparison.png")
