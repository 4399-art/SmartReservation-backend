from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.model.user import User
from app.schemas.user import UserResponse, UserUpdateRequest
from app.service import user_service

router = APIRouter(prefix="/user", tags=["用户管理"])


@router.get("/info")
def get_my_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = user_service.get_user(current_user.id, db)
    return Response.success(data=result)


@router.put("/info")
def update_my_info(
    data: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = user_service.update_user(current_user.id, data, db)
    return Response.success(data=result)