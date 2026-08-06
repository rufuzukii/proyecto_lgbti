from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field, SecretStr

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class UserRole(StrEnum):
    ANONYMOUS = "anonymous"
    ADMIN = "admin"
    COMMON = "common"


class UserType(StrEnum):
    ADMIN = "admin"
    RRHH = "rrhh"
    DOCENTE = "docente"
    POLITICO = "politico"
    SOCIOLOGO = "sociologo"
    ONG = "ong"
    COMUN = "comun"


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr = Field(max_length=254, examples=["user@example.com"])
    password: SecretStr = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
    )
    organization: str | None = Field(default=None, max_length=120)
    user_type: UserType | None = None


class UserRead(BaseModel):
    id: str
    username: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=80)
    email: str | None = Field(default=None, examples=["user@example.com"])
    role: UserRole = UserRole.COMMON
    organization: str | None = None
    user_type: UserType | None = None
    version: str = ""
    active: bool = True
    email_verified: bool = True
    session_version: int = 0
