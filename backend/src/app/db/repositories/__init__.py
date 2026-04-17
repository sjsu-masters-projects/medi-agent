"""Focused repository classes for backend data access."""

from app.db.repositories.care_teams import CareTeamRepository
from app.db.repositories.clinicians import ClinicianRepository
from app.db.repositories.clinics import ClinicRepository

__all__ = [
    "CareTeamRepository",
    "ClinicianRepository",
    "ClinicRepository",
]
