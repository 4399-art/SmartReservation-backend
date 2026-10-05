from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user
from app.model.user import User
from app.schemas.seat import SeatCreateRequest, SeatUpdateRequest
from app.service import seat_service

router = APIRouter(prefix="/seat", tags=["座位管理"])


@router.get("/list")
def get_seat_list(
    page: int = 1,
    page_size: int = 10,
    keywords: str | None = None,
    space_id: int | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = seat_service.get_seat_page_list(db, page, page_size, keywords, space_id)
    return Response.success(data=res)


@router.post("")
def create_seat(
    data: SeatCreateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = seat_service.create_seat(db, data)
    return Response.success(data=res)


@router.put("/{seat_id}")
def update_seat(
    seat_id: int,
    data: SeatUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = seat_service.update_seat(db, seat_id, data)
    return Response.success(data=res)


@router.delete("/{seat_id}")
def delete_seat(
    seat_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    seat_service.delete_seat(db, seat_id)
    return Response.success(message="删除成功")


@router.get("/space/{space_id}")
def get_seats_by_space(
    space_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = seat_service.get_seats_by_space(db, space_id)
    return Response.success(data=res)