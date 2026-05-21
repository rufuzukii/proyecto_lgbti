from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    ANONYMOUS = "anonymous"
    ADMIN = "admin"
    USER = "user"


class UserType(str, Enum):
    RRHH = "rrhh"
    PROFESOR = "profesor"
    COMUN = "comun"


class UserBase(BaseModel):
    email: Optional[str] = Field(default=None, examples=["user@example.com"])
    role: UserRole = UserRole.USER
    user_type: Optional[UserType] = None


class UserRegister(UserBase):
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase):
    id: int
    name: str

