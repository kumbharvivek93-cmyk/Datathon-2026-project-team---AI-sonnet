"""Public model imports for application modules and Flask-Migrate discovery."""

from app.models.core import (
    CrimeIncident,
    CrimeLink,
    FIRDetail,
    Location,
    Person,
    Role,
    SocioEconomicData,
    Suspect,
    User,
    Victim,
)

__all__ = [
    "CrimeIncident",
    "CrimeLink",
    "FIRDetail",
    "Location",
    "Person",
    "Role",
    "SocioEconomicData",
    "Suspect",
    "User",
    "Victim",
]
