"""Email preference requests; no arbitrary recipients or redirect URLs."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class EmailPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: StrictBool = False
    appointments: StrictBool = False
    care_plans: StrictBool = False
    records: StrictBool = False
    reviews: StrictBool = False


class EmailVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")


class EmailInvitationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128)


class EmailPreferencesRead(BaseModel):
    email: str
    verified: bool
    synthetic: bool
    preferences: EmailPreferences
    # False until the email migrations are installed; portals show a calm notice.
    available: bool = True
