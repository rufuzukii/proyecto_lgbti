from fastapi import APIRouter

from app.modules.account.users.schemas import UserRead
from app.modules.account.users.service import list_users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserRead])
def list_users_endpoint() -> list[UserRead]:
    return list_users()
