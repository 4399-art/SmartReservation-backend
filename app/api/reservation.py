from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user
from app.model.user import User
from pydantic import BaseModel
from app.schemas.reservation import ReservationAuditRequest, ReservationCreateRequest
from app.service import reservation_service

router = APIRouter(prefix="/reservation", tags=["预约管理"])


@router.post("")
def create_reservation(
    data: ReservationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = reservation_service.create_reservation(db, data, current_user.id)
    return Response.success(data=res, message="预约提交成功")


@router.get("/my")
def get_my_reservations(
    page: int = 1,
    page_size: int = 10,
    status: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = reservation_service.get_my_reservations(db, current_user.id, page, page_size, status)
    return Response.success(data=res)


@router.put("/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation_service.cancel_reservation(db, reservation_id, current_user.id)
    return Response.success(message="取消成功")


@router.get("/list")
def get_all_reservations(
    page: int = 1,
    page_size: int = 10,
    status: int | None = Query(default=None),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = reservation_service.get_all_reservations(db, page, page_size, status)
    return Response.success(data=res)


@router.put("/{reservation_id}/audit")
def audit_reservation(
    reservation_id: int,
    data: ReservationAuditRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    reservation_service.audit_reservation(db, reservation_id, data)
    return Response.success(message="审核完成")


class BatchAuditRequest(BaseModel):
    ids: list[int]
    status: int
    audit_remark: str | None = None


@router.put("/batch-audit")
def batch_audit_reservations(
    data: BatchAuditRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = reservation_service.batch_audit_reservations(db, data.ids, data.status, data.audit_remark)
    return Response.success(data=res, message=f"完成：成功 {res['success_count']} 条")
