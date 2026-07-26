"""Interactive relationship graph backed by recorded crime links."""

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from app.models.core import CrimeIncident, CrimeLink, Suspect

network_bp = Blueprint("network", __name__)


def graph_payload():
    nodes, edges, seen = [], [], set()
    for link in CrimeLink.query.limit(300).all():
        suspect = link.suspect
        crime = link.crime
        if suspect and suspect.id not in seen:
            seen.add(suspect.id)
            nodes.append({"data": {"id": f"s{suspect.id}", "label": suspect.person.name if suspect.person else f"Suspect {suspect.id}", "kind": "suspect", "risk": suspect.risk_score}})
        if crime and f"c{crime.id}" not in seen:
            seen.add(f"c{crime.id}")
            nodes.append({"data": {"id": f"c{crime.id}", "label": crime.crime_number, "kind": "crime", "district": crime.district}})
        if suspect and crime:
            edges.append({"data": {"id": f"e{link.id}", "source": f"s{suspect.id}", "target": f"c{crime.id}", "label": link.relationship or "Associated"}})
    return {"elements": {"nodes": nodes, "edges": edges}, "summary": {"nodes": len(nodes), "links": len(edges)}}


@network_bp.get("/network")
@login_required
def index():
    return render_template("network/index.html", page_title="Criminal Networks", graph=graph_payload())


@network_bp.get("/api/network")
def api_network():
    return jsonify(graph_payload())
