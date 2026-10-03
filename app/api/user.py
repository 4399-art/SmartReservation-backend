from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_user, get_current_admin
from app.model.user import User
from app.schemas.user import UserCreateRequest, UserResponse, UserUpdateRequest, PasswordUpdateRequest
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
    result = user_service.update_user_info(current_user.id, data, db)
    return Response.success(data=result)

@router.put("/password")
def update_password(
    data: PasswordUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    user_service.update_password(current_user.id, data, db)
    return Response.success(message="密码更新成功")

# 分页查询用户 支持模糊查询用户名
@router.get("/list")
def get_user_list(
    page: int = 1,
    page_size: int = 10,
    keywords: str | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = user_service.get_user_page_list(db, page, page_size, keywords)
    return Response.success(data=res)


@router.post("")
def create_user(
    data: UserCreateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = user_service.create_user(db, data)
    return Response.success(data=res)

@router.put("/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = user_service.update_user(db, user_id, data, current_user)
    return Response.success(data=res)

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = user_service.delete_user(db, user_id, current_user)
    return Response.success(message="删除成功")