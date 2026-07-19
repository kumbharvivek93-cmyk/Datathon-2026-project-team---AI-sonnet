# Crime Intelligence & Analytical Platform

A Flask-based decision-support platform for fictional Karnataka State Police/SCRB demonstration data. It consolidates crime records, map intelligence, relationship networks, explainable analytical signals, and report downloads in one responsive dashboard.

## Included capabilities

- Secure session login with admin, officer, and analyst roles, password hashing and CSRF protection.
- Crime registry, case details, filtered and natural-language-style intelligence search.
- Command dashboard with operational metrics, Chart.js trends, category analysis, and a Leaflet incident map.
- Criminal relationship graph using Cytoscape.js; offender profile and case timeline.
- Pattern discovery, anomaly detection, hotspot density, social indicators, and explainable monthly crime-volume estimates.
- REST endpoints: `/api/crimes`, `/api/suspects`, `/api/dashboard`, `/api/network`, `/api/predictions`, `/api/hotspots`, and `/api/reports`.
- CSV and Excel downloads, Docker files, SQLite development support, PostgreSQL production configuration, and a deterministic fictional-data generator.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m flask --app run seed-demo
python run.py
```

Open `http://127.0.0.1:5000`. The development default account is `admin` / `ChangeMe123!`; change these environment values before any real deployment.

## Notes

The seed data is entirely fictional. The prediction and risk features are transparent decision-support heuristics, not automated enforcement or adjudication systems. Use Flask-Migrate in production instead of automatic schema creation, set a unique `SECRET_KEY`, turn on secure cookies, and use PostgreSQL.
