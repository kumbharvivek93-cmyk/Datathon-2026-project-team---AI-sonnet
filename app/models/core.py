"""Core SQLAlchemy models shared by dashboard, analytics, and API modules."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from flask_login import UserMixin

from app.extensions import db


class Role(str, Enum):
    """Roles supported by the role-based access-control layer."""

    ADMIN = "admin"
    OFFICER = "officer"
    ANALYST = "analyst"


class TimestampMixin:
    """Add auditable creation and update timestamps to a database model."""

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class User(UserMixin, TimestampMixin, db.Model):
    """An authenticated platform user with one of the supported roles."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    full_name = db.Column(db.String(160), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.OFFICER.value, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        """Store a securely hashed password rather than the password itself."""
        from app.services.security import hash_password

        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        """Return whether a candidate password matches this user's hash."""
        from app.services.security import verify_password

        return verify_password(self.password_hash, password)

    def has_role(self, *roles: Role | str) -> bool:
        """Return whether the user has any supplied role."""
        normalized_roles = {
            role.value if isinstance(role, Role) else str(role).lower()
            for role in roles
        }
        return self.role.lower() in normalized_roles

    @property
    def is_admin(self) -> bool:
        """Convenience property used by templates and privileged routes."""
        return self.has_role(Role.ADMIN)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Location(TimestampMixin, db.Model):
    """A geographic location in Karnataka used by one or more incidents."""

    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=False, index=True)
    taluk = db.Column(db.String(100), nullable=True, index=True)
    village = db.Column(db.String(120), nullable=True, index=True)
    police_station = db.Column(db.String(120), nullable=True, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    incidents = db.relationship("CrimeIncident", back_populates="location")

    def __repr__(self) -> str:
        return f"<Location {self.district}/{self.taluk or '-'}>"


class CrimeIncident(TimestampMixin, db.Model):
    """A recorded crime incident and its core investigative attributes."""

    __tablename__ = "crime_incidents"

    id = db.Column(db.Integer, primary_key=True)
    crime_number = db.Column(db.String(80), nullable=False, unique=True, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time, nullable=True)
    district = db.Column(db.String(100), nullable=False, index=True)
    police_station = db.Column(db.String(120), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    crime_type = db.Column(db.String(100), nullable=False, index=True)
    ipc_sections = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="Pending", index=True)
    modus_operandi = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)

    location = db.relationship("Location", back_populates="incidents")
    links = db.relationship(
        "CrimeLink",
        back_populates="crime",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    fir_detail = db.relationship(
        "FIRDetail", back_populates="incident", uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CrimeIncident {self.crime_number}>"


class FIRDetail(TimestampMixin, db.Model):
    """Statutory-style FIR information associated with one crime incident.

    The core incident table remains the common investigation record; this
    separate table lets an existing database gain FIR capture without changing
    its established incident columns.
    """

    __tablename__ = "fir_details"

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(
        db.Integer, db.ForeignKey("crime_incidents.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    informant_name = db.Column(db.String(160), nullable=False)
    informant_address = db.Column(db.Text, nullable=False)
    informant_phone = db.Column(db.String(30), nullable=True)
    informant_age = db.Column(db.Integer, nullable=True)
    informant_gender = db.Column(db.String(30), nullable=True)
    report_date = db.Column(db.Date, nullable=False)
    report_time = db.Column(db.Time, nullable=True)
    occurrence_end_date = db.Column(db.Date, nullable=True)
    occurrence_end_time = db.Column(db.Time, nullable=True)
    place_of_occurrence = db.Column(db.Text, nullable=False)
    distance_direction_from_station = db.Column(db.String(200), nullable=True)
    complaint_text = db.Column(db.Text, nullable=False)
    delay_reason = db.Column(db.Text, nullable=True)
    accused_details = db.Column(db.Text, nullable=True)
    property_details = db.Column(db.Text, nullable=True)
    injuries_or_death = db.Column(db.Text, nullable=True)
    action_taken = db.Column(db.Text, nullable=True)
    recording_officer = db.Column(db.String(160), nullable=False)
    officer_designation = db.Column(db.String(160), nullable=True)

    incident = db.relationship("CrimeIncident", back_populates="fir_detail")


class Person(TimestampMixin, db.Model):
    """A person who can be linked to a suspect or victim profile."""

    __tablename__ = "persons"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(30), nullable=True, index=True)
    aadhaar = db.Column(db.String(20), nullable=True, index=True)
    phone = db.Column(db.String(30), nullable=True, index=True)

    suspect = db.relationship(
        "Suspect",
        back_populates="person",
        uselist=False,
        cascade="all, delete-orphan",
    )
    victim = db.relationship(
        "Victim",
        back_populates="person",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Person {self.name}>"


class Suspect(TimestampMixin, db.Model):
    """A suspect profile connected to a canonical person record."""

    __tablename__ = "suspects"
    __table_args__ = (
        db.CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_risk_score"),
    )

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(
        db.Integer,
        db.ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    gang_name = db.Column(db.String(160), nullable=True, index=True)
    risk_score = db.Column(db.Float, nullable=False, default=0.0, index=True)
    repeat_offender = db.Column(db.Boolean, nullable=False, default=False, index=True)
    wanted_level = db.Column(db.String(40), nullable=True, index=True)
    aliases = db.Column(db.Text, nullable=True)
    photo_url = db.Column(db.String(500), nullable=True)

    person = db.relationship("Person", back_populates="suspect")
    crime_links = db.relationship(
        "CrimeLink",
        foreign_keys="CrimeLink.suspect_id",
        back_populates="suspect",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Suspect person_id={self.person_id}>"


class Victim(TimestampMixin, db.Model):
    """A victim profile connected to a canonical person record."""

    __tablename__ = "victims"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(
        db.Integer,
        db.ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    person = db.relationship("Person", back_populates="victim")
    crime_links = db.relationship(
        "CrimeLink",
        foreign_keys="CrimeLink.victim_id",
        back_populates="victim",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Victim person_id={self.person_id}>"


class CrimeLink(TimestampMixin, db.Model):
    """An evidentiary relationship among an incident, suspect, and victim."""

    __tablename__ = "crime_links"

    id = db.Column(db.Integer, primary_key=True)
    crime_id = db.Column(
        db.Integer,
        db.ForeignKey("crime_incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suspect_id = db.Column(
        db.Integer,
        db.ForeignKey("suspects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    victim_id = db.Column(
        db.Integer,
        db.ForeignKey("victims.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    relationship = db.Column(db.String(100), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)

    crime = db.relationship("CrimeIncident", back_populates="links")
    suspect = db.relationship("Suspect", back_populates="crime_links")
    victim = db.relationship("Victim", back_populates="crime_links")

    def __repr__(self) -> str:
        return f"<CrimeLink crime_id={self.crime_id} suspect_id={self.suspect_id}>"


class SocioEconomicData(TimestampMixin, db.Model):
    """District-level contextual indicators used for crime correlation analysis."""

    __tablename__ = "socio_economic_data"
    __table_args__ = (
        db.UniqueConstraint("district", "year", name="uq_socio_economic_district_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, default=lambda: datetime.utcnow().year)
    population = db.Column(db.Integer, nullable=True)
    literacy = db.Column(db.Float, nullable=True)
    urbanization = db.Column(db.Float, nullable=True)
    poverty_index = db.Column(db.Float, nullable=True)
    unemployment = db.Column(db.Float, nullable=True)
    education_index = db.Column(db.Float, nullable=True)

    def __repr__(self) -> str:
        return f"<SocioEconomicData {self.district}/{self.year}>"
