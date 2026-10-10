"""Enterprise HR, accounting, BI and biometric tables for SUFRA.

Kept separate from the core restaurant models so the upgrade is additive and
safe against an existing nova.db. Importing this module registers the tables
with SQLModel.metadata; enterprise.ensure_schema() creates them.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class HRProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True, unique=True)
    employee_no: str = Field(default="", index=True)
    work_email: str = ""
    phone: str = ""
    photo_url: str = ""
    department: str = "Operations"
    job_title: str = ""
    contract_type: str = "Permanent"   # Permanent | Part time | Casual | Contractor
    contracted_hours: float = 40.0
    status: str = "active"             # active | leave | suspended | leaver
    manager_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    emergency_contact: str = ""
    notes: str = ""
    started_on: Optional[date] = None
    biometric_enabled: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AttendanceRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True)
    day: date = Field(default_factory=date.today, index=True)
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    break_minutes: int = 0
    status: str = "present"             # present | late | absent | sick | training
    source: str = "manual"              # manual | tablet | biometric
    note: str = ""
    approved_by: Optional[int] = Field(default=None, foreign_key="staff.id")
    created_at: datetime = Field(default_factory=datetime.now)


class LeaveRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True)
    leave_type: str = "annual"           # annual | sick | unpaid | parental | compassionate
    start_on: date
    end_on: date
    days: float = 1.0
    status: str = "pending"              # pending | approved | rejected | cancelled
    note: str = ""
    requested_at: datetime = Field(default_factory=datetime.now)
    decided_at: Optional[datetime] = None
    decided_by: Optional[int] = Field(default=None, foreign_key="staff.id")


class TrainingRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True)
    course: str
    provider: str = "SUFRA Academy"
    category: str = "operations"        # operations | food_safety | service | leadership | compliance
    due_on: Optional[date] = None
    completed_on: Optional[date] = None
    expires_on: Optional[date] = None
    score: float = 0.0
    status: str = "assigned"            # assigned | in_progress | complete | expired
    certificate: str = ""
    note: str = ""


class PerformanceReview(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True)
    reviewer_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    period: str = ""
    rating: float = 0.0
    service_score: float = 0.0
    reliability_score: float = 0.0
    goals: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class ChartAccount(SQLModel, table=True):
    code: str = Field(primary_key=True)
    name: str
    account_type: str                   # asset | liability | equity | revenue | expense
    normal_side: str = "debit"         # debit | credit
    group_name: str = ""
    active: bool = True


class JournalEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)
    description: str = ""
    reference: str = Field(default="", index=True)
    source: str = "manual"              # manual | sales | inventory | payroll | waste
    posted: bool = True
    created_by: Optional[int] = Field(default=None, foreign_key="staff.id")
    created_at: datetime = Field(default_factory=datetime.now)


class JournalLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    journal_id: int = Field(foreign_key="journalentry.id", index=True)
    account_code: str = Field(foreign_key="chartaccount.code", index=True)
    debit: float = 0.0
    credit: float = 0.0
    memo: str = ""


class BiometricCredential(SQLModel, table=True):
    """A WebAuthn public-key credential. No facial image/template is stored.

    Face ID / Touch ID / Windows Hello stay on the employee's own device; the
    server stores only the public credential required to verify a signed login.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True)
    credential_id: str = Field(index=True, unique=True)
    public_key_b64: str
    sign_count: int = 0
    label: str = "Device biometric"
    created_at: datetime = Field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None


class BiometricChallenge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id", index=True)
    kind: str                           # register | authenticate
    challenge_b64: str
    rp_id: str
    origin: str
    expires_at: datetime
