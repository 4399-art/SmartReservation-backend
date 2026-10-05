from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user
from app.model.user import User
from app.schemas.space import SpaceCreateRequest, SpaceUpdateRequest
from app.service import space_service

router = APIRouter(prefix="/space", tags=["区域管理"])


@router.get("/all-open")
def get_open_spaces(
    keywords: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = space_service.get_open_spaces(db, keywords)
    return Response.success(data=res)


@router.get("/all")
def get_all_spaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = space_service.get_all_spaces(db)
    return Response.success(data=res)


@router.get("/list")
def get_space_list(
    page: int = 1,
    page_size: int = 10,
    keywords: str | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = space_service.get_space_page_list(db, page, page_size, keywords)
    return Response.success(data=res)


@router.post("")
def create_space(
    data: SpaceCreateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = space_service.create_space(db, data)
    return Response.success(data=res)


@router.put("/{space_id}")
def update_space(
    space_id: int,
    data: SpaceUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = space_service.update_space(db, space_id, data)
    return Response.success(data=res)


@router.delete("/{space_id}")
def delete_space(
    space_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    space_service.delete_space(db, space_id)
    return Response.success(message="删除成功")