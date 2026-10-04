from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.equipment import Equipment
from app.model.lab import Lab
from app.model.reservation import Reservation, ReservationStatus
from app.schemas.reservation import (
    ReservationAuditRequest,
    ReservationCreateRequest,
    ReservationResponse,
)


def _fill_names(r: Reservation) -> dict:
    resp = ReservationResponse.model_validate(r).model_dump()
    if r.lab:
        resp["lab_name"] = r.lab.name
    if r.equipment:
        resp["equipment_name"] = r.equipment.name
    if r.user:
        resp["user_name"] = r.user.name
    return resp


def _check_conflict(
    db: Session,
    lab_id: int,
    equipment_id: int | None,
    date: str,
    start_time: str,
    end_time: str,
    exclude_id: int | None = None,
) -> None:
    query = db.query(Reservation).filter(
        Reservation.date == date,
        Reservation.lab_id == lab_id,
        Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
    )
    if equipment_id:
        query = query.filter(Reservation.equipment_id == equipment_id)
    else:
        query = query.filter(Reservation.equipment_id.is_(None))

    if exclude_id:
        query = query.filter(Reservation.id != exclude_id)

    existing = query.all()

    for r in existing:
        if start_time < r.end_time and end_time > r.start_time:
            target = f"设备(ID:{equipment_id})" if equipment_id else f"实验室(ID:{lab_id})"
            raise BusinessException(message=f"该时段已被预约")


def create_reservation(
    db: Session, data: ReservationCreateRequest, user_id: int
) -> dict:
    lab = db.query(Lab).filter(Lab.id == data.lab_id).first()
    if not lab:
        raise BusinessException(message="实验室不存在")
    if lab.status != 1:
        raise BusinessException(message="实验室已关闭，无法预约")

    equipment_id = data.equipment_id
    if equipment_id:
        eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
        if not eq:
            raise BusinessException(message="设备不存在")
        if eq.status != 1:
            raise BusinessException(message="设备维修中，无法预约")
        if eq.lab_id != data.lab_id:
            raise BusinessException(message="该设备不属于此实验室")

    _check_conflict(db, data.lab_id, equipment_id, data.date, data.start_time, data.end_time)

    reservation = Reservation(
        user_id=user_id,
        lab_id=data.lab_id,
        equipment_id=equipment_id,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        remark=data.remark,
        status=ReservationStatus.PENDING,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return _fill_names(reservation)


def get_my_reservations(
    db: Session,
    user_id: int,
    page: int,
    page_size: int,
    status: int | None = None,
) -> PageResponse:
    query = (
        db.query(Reservation)
        .filter(Reservation.user_id == user_id)
        .order_by(Reservation.id.desc())
    )
    if status is not None:
        query = query.filter(Reservation.status == status)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PageResponse(
        list=[_fill_names(r) for r in items], total=total
    )


def cancel_reservation(db: Session, reservation_id: int, user_id: int) -> None:
    r = (
        db.query(Reservation)
        .filter(Reservation.id == reservation_id, Reservation.user_id == user_id)
        .first()
    )
    if not r:
        raise BusinessException(message="预约记录不存在")
    if r.status in (ReservationStatus.PENDING, ReservationStatus.APPROVED):
        r.status = ReservationStatus.CANCELLED
        db.commit()
    elif r.status == ReservationStatus.CANCELLED:
        raise BusinessException(message="已取消，不能重复操作")
    elif r.status == ReservationStatus.REJECTED:
        raise BusinessException(message="已拒绝的预约不能取消")


def get_all_reservations(
    db: Session,
    page: int,
    page_size: int,
    status: int | None = None,
) -> PageResponse:
    query = db.query(Reservation).order_by(Reservation.id.desc())
    if status is not None:
        query = query.filter(Reservation.status == status)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PageResponse(
        list=[_fill_names(r) for r in items], total=total
    )


def audit_reservation(
    db: Session,
    reservation_id: int,
    data: ReservationAuditRequest,
) -> None:
    r = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not r:
        raise BusinessException(message="预约记录不存在")
    if r.status not in (ReservationStatus.PENDING, ReservationStatus.APPROVED):
        raise BusinessException(message="当前状态不可审核")
    if data.status not in (ReservationStatus.APPROVED, ReservationStatus.REJECTED):
        raise BusinessException(message="审核状态无效")

    if data.status == ReservationStatus.APPROVED:
        _check_conflict(
            db, r.lab_id, r.equipment_id, r.date, r.start_time, r.end_time, exclude_id=r.id
        )

    r.status = data.status
    r.audit_remark = data.audit_remark
    db.commit()


def batch_audit_reservations(
    db: Session,
    ids: list[int],
    status: int,
    audit_remark: str | None = None,
) -> dict:
    if status not in (ReservationStatus.APPROVED, ReservationStatus.REJECTED):
        raise BusinessException(message="审核状态无效")
    success_count = 0
    errors = []
    for rid in ids:
        r = db.query(Reservation).filter(Reservation.id == rid).first()
        if not r:
            errors.append({"id": rid, "reason": "预约不存在"})
            continue
        if r.status not in (ReservationStatus.PENDING, ReservationStatus.APPROVED):
            errors.append({"id": rid, "reason": f"当前状态不可审核"})
            continue
        if status == ReservationStatus.APPROVED:
            try:
                _check_conflict(db, r.lab_id, r.equipment_id, r.date, r.start_time, r.end_time, exclude_id=r.id)
            except BusinessException as e:
                errors.append({"id": rid, "reason": e.message})
                continue
        r.status = status
        r.audit_remark = audit_remark
        success_count += 1
    db.commit()
    return {"success_count": success_count, "errors": errors}
