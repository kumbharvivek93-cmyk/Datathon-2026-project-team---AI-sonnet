"""Downloadable, filtered CSV and XLSX report output."""

import csv
from io import BytesIO, StringIO

from flask import Blueprint, Response, jsonify, render_template, request, send_file
from flask_login import login_required

from app.api.serializers import filter_crimes
from app.models.core import CrimeIncident

reports_bp = Blueprint("reports", __name__)


def _records():
    return filter_crimes(CrimeIncident.query.all(), request.args)


@reports_bp.get("/reports")
@login_required
def index():
    return render_template("reports/index.html", page_title="Reports", total=len(CrimeIncident.query.all()))


@reports_bp.get("/api/reports")
def report_api():
    rows = _records()
    return jsonify({"data": [{"crime_number": r.crime_number, "date": r.date.isoformat(), "district": r.district, "crime_type": r.crime_type, "status": r.status} for r in rows], "total": len(rows)})


@reports_bp.get("/reports/download/<format>")
@login_required
def download(format: str):
    rows = _records()
    headers = ["Crime Number", "Date", "District", "Police Station", "Crime Type", "Status", "IPC Sections"]
    values = [[r.crime_number, r.date.isoformat(), r.district, r.police_station, r.crime_type, r.status, r.ipc_sections or ""] for r in rows]
    if format == "csv":
        output = StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows(values)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=crime-report.csv"})
    if format == "xlsx":
        from openpyxl import Workbook
        book = Workbook(); sheet = book.active; sheet.title = "Crime Report"; sheet.append(headers)
        for row in values: sheet.append(row)
        output = BytesIO(); book.save(output); output.seek(0)
        return send_file(output, as_attachment=True, download_name="crime-report.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return jsonify({"error": "Supported formats are csv and xlsx."}), 400
