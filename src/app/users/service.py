from dataclasses import dataclass
from typing import List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from app.users.schemas import UserRead, UserRegister, UserRole, UserType


@dataclass
class UserRecord:
    id: int
    name: str
    email: Optional[str]
    role: UserRole
    user_type: Optional[UserType]
    password_hash: str


_USERS: List[UserRecord] = []


def list_users() -> list[UserRead]:
    return [
        UserRead(id=user.id, name=user.name, email=user.email, role=user.role, user_type=user.user_type)
        for user in _USERS
    ]


def get_user(user_id: int) -> Optional[UserRead]:
    for user in _USERS:
        if user.id == user_id:
            return UserRead(
                id=user.id,
                name=user.name,
                email=user.email,
                role=user.role,
                user_type=user.user_type,
            )
    return None


def get_user_record_by_email(email: str) -> Optional[UserRecord]:
    for user in _USERS:
        if user.email == email:
            return user
    return None


def create_user(payload: UserRegister) -> UserRead:
    new_id = (_USERS[-1].id + 1) if _USERS else 1
    role = payload.role
    user_type = payload.user_type

    if role == UserRole.ADMIN:
        user_type = None
    elif role == UserRole.USER and user_type is None:
        user_type = UserType.COMUN

    record = UserRecord(
        id=new_id,
        name=payload.name,
        email=payload.email,
        role=role,
        user_type=user_type,
        password_hash=generate_password_hash(payload.password),
    )
    _USERS.append(record)
    return UserRead(id=record.id, name=record.name, email=record.email, role=record.role, user_type=record.user_type)


def authenticate_user(email: str, password: str) -> Optional[UserRecord]:
    if not email or not password:
        return None
    record = get_user_record_by_email(email)
    if record is None:
        return None
    if not check_password_hash(record.password_hash, password):
        return None
    return record
