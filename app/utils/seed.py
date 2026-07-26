"""Deterministic, fictional data used by the local demonstration environment.

The generator deliberately avoids real people, identifiers, addresses, or case
numbers.  It gives a newly installed instance enough density to demonstrate the
map, charts, network graph, and machine-learning endpoints immediately.
"""

from __future__ import annotations

from datetime import date, time, timedelta
import random

from sqlalchemy import func

from app.extensions import db
from app.models.core import (
    CrimeIncident,
    CrimeLink,
    Location,
    Person,
    SocioEconomicData,
    Suspect,
    Victim,
)


# Karnataka district centres, used solely to create believable map coordinates.
DISTRICTS = {
    "Bagalkote": (16.1816, 75.6966),
    "Ballari": (15.1394, 76.9214),
    "Belagavi": (15.8497, 74.4977),
    "Bengaluru Rural": (13.2257, 77.5750),
    "Bengaluru Urban": (12.9716, 77.5946),
    "Bidar": (17.9104, 77.5199),
    "Chamarajanagar": (11.9261, 76.9437),
    "Chikkaballapur": (13.4355, 77.7315),
    "Chikkamagaluru": (13.3161, 75.7720),
    "Chitradurga": (14.2251, 76.4005),
    "Dakshina Kannada": (12.9141, 74.8560),
    "Davanagere": (14.4644, 75.9218),
    "Dharwad": (15.4589, 75.0078),
    "Gadag": (15.4325, 75.6380),
    "Hassan": (13.0068, 76.1000),
    "Haveri": (14.7951, 75.3991),
    "Kalaburagi": (17.3297, 76.8343),
    "Kodagu": (12.3375, 75.8069),
    "Kolar": (13.1357, 78.1339),
    "Koppal": (15.3505, 76.1567),
    "Mandya": (12.5222, 76.9009),
    "Mysuru": (12.2958, 76.6394),
    "Raichur": (16.2076, 77.3463),
    "Ramanagara": (12.7211, 77.2799),
    "Shivamogga": (13.9299, 75.5681),
    "Tumakuru": (13.3409, 77.1010),
    "Udupi": (13.3409, 74.7421),
    "Uttara Kannada": (14.7937, 74.6869),
    "Vijayapura": (16.8302, 75.7100),
    "Vijayanagara": (15.3350, 76.4600),
    "Yadgir": (16.7626, 77.1442),
}

CRIME_TYPES = (
    "Theft",
    "Burglary",
    "Robbery",
    "Assault",
    "Cyber Crime",
    "Fraud",
    "Vehicle Theft",
    "Missing Person",
    "Narcotics",
    "Domestic Violence",
)
STATUSES = ("Open", "Under Investigation", "Solved", "Closed")
MODI = (
    "Forced entry after dark",
    "Deceptive digital payment request",
    "Two-wheeler reconnaissance",
    "Impersonation of an official",
    "Crowded-market distraction",
    "Coordinated phone contact",
    "Opportunistic street offence",
)
FIRST_NAMES = (
    "Aarav", "Ananya", "Arjun", "Bhavana", "Darshan", "Deepa", "Farhan",
    "Gowri", "Harish", "Ishita", "Kiran", "Lakshmi", "Manoj", "Nandini",
    "Pranav", "Pooja", "Ravi", "Sahana", "Vikram", "Yash",
)
LAST_NAMES = (
    "Kumar", "Rao", "Shetty", "Gowda", "Naik", "Bhat", "Patil", "Reddy",
    "Hegde", "Kulkarni", "Khan", "Sharma",
)
GANGS = ("", "North Gate Crew", "Coastal Circle", "Sandalwood Unit", "False Axis")


def _station_name(district: str, index: int) -> str:
    return f"{district} {('Central', 'North', 'South', 'East', 'West')[index % 5]} PS"


def _person_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def seed_demo_data(
    incident_count: int = 1000,
    suspect_count: int = 300,
    victim_count: int = 500,
    force: bool = False,
) -> dict[str, int]:
    """Populate a fresh database with realistic-but-fictional demo records.

    It is intentionally idempotent unless ``force`` is passed by an operator.
    A stable random seed makes dashboard screenshots and test expectations
    reproducible.
    """
    existing = db.session.scalar(db.select(func.count()).select_from(CrimeIncident))
    if existing and not force:
        return {"incidents": int(existing), "created": 0}

    if force:
        # This is intentionally not a public web action.  It is used only by a
        # local CLI command where administrators explicitly request a reset.
        CrimeLink.query.delete()
        Suspect.query.delete()
        Victim.query.delete()
        Person.query.delete()
        CrimeIncident.query.delete()
        Location.query.delete()
        SocioEconomicData.query.delete()
        db.session.commit()

    rng = random.Random(20260719)
    districts = list(DISTRICTS.items())

    locations: list[Location] = []
    socioeconomic: list[SocioEconomicData] = []
    for ordinal, (district, (latitude, longitude)) in enumerate(districts):
        locations.append(
            Location(
                district=district,
                taluk=f"{district} Taluk",
                village=f"{district} Sector {ordinal % 7 + 1}",
                latitude=latitude,
                longitude=longitude,
            )
        )
        socioeconomic.append(
            SocioEconomicData(
                district=district,
                population=rng.randint(180_000, 12_500_000),
                literacy=round(rng.uniform(62.0, 92.0), 2),
                urbanization=round(rng.uniform(20.0, 96.0), 2),
                poverty_index=round(rng.uniform(5.0, 32.0), 2),
                unemployment=round(rng.uniform(1.4, 10.6), 2),
                education_index=round(rng.uniform(0.46, 0.88), 3),
            )
        )
    db.session.add_all(locations + socioeconomic)

    suspects: list[Suspect] = []
    victims: list[Victim] = []
    for index in range(suspect_count + victim_count):
        person = Person(
            name=_person_name(rng),
            age=rng.randint(19, 64),
            gender=rng.choice(("Male", "Female", "Other")),
            aadhaar=None,
            phone=f"9{rng.randint(100000000, 999999999)}",
        )
        db.session.add(person)
        if index < suspect_count:
            suspects.append(
                Suspect(
                    person=person,
                    gang_name=rng.choice(GANGS),
                    risk_score=round(rng.uniform(20, 96), 1),
                    repeat_offender=rng.random() < 0.42,
                    wanted_level=rng.choice(("Low", "Medium", "High")),
                )
            )
        else:
            victims.append(Victim(person=person))
    db.session.add_all(suspects + victims)
    db.session.flush()

    start = date.today() - timedelta(days=730)
    incidents: list[CrimeIncident] = []
    for index in range(incident_count):
        district, (center_lat, center_lon) = rng.choice(districts)
        crime_type = rng.choices(
            CRIME_TYPES,
            weights=(25, 12, 9, 11, 11, 10, 8, 5, 4, 5),
            k=1,
        )[0]
        status = rng.choices(STATUSES, weights=(18, 22, 45, 15), k=1)[0]
        incident_day = start + timedelta(days=rng.randrange(731))
        incidents.append(
            CrimeIncident(
                crime_number=f"KSP-{incident_day:%Y}-{index + 1:05d}",
                date=incident_day,
                time=time(rng.randrange(24), rng.choice((0, 15, 30, 45))),
                district=district,
                police_station=_station_name(district, index),
                latitude=round(center_lat + rng.uniform(-0.07, 0.07), 6),
                longitude=round(center_lon + rng.uniform(-0.07, 0.07), 6),
                crime_type=crime_type,
                ipc_sections=rng.choice(("IPC 379", "IPC 392", "IPC 420", "IPC 323", "IPC 354", "IT Act 66C")),
                status=status,
                modus_operandi=rng.choice(MODI),
                description=(
                    f"Fictional demonstration record: reported {crime_type.lower()} "
                    f"incident in {district}."
                ),
            )
        )
    db.session.add_all(incidents)
    db.session.flush()

    links: list[CrimeLink] = []
    for incident in incidents:
        if rng.random() < 0.62:
            suspect = rng.choice(suspects)
            victim = rng.choice(victims)
            links.append(
                CrimeLink(
                    crime_id=incident.id,
                    suspect_id=suspect.id,
                    victim_id=victim.id,
                    relationship=rng.choice(
                        ("Associate", "Co-offender", "Phone Contact", "Visited Same Location")
                    ),
                )
            )
    db.session.add_all(links)
    db.session.commit()
    return {
        "incidents": len(incidents),
        "suspects": len(suspects),
        "victims": len(victims),
        "links": len(links),
        "created": len(incidents),
    }
