from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    ANONYMOUS = "anonymous"
    ADMIN = "admin"
    COMMON = "common"


class UserType(str, Enum):
    RRHH = "rrhh"
    PROFESOR = "profesor"
    COMUN = "comun"


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=254, examples=["user@example.com"])
    password: str = Field(min_length=8, max_length=32)
    organization: Optional[str] = Field(default=None, max_length=120)
    user_type: Optional[UserType] = None


class UserRead(BaseModel):
    id: str
    username: Optional[str] = Field(default=None, min_length=2, max_length=80)
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    email: Optional[str] = Field(default=None, examples=["user@example.com"])
    role: UserRole = UserRole.COMMON
    organization: Optional[str] = None
    user_type: Optional[UserType] = None

