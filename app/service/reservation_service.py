from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.seat import Seat
from app.model.space import Space
from app.model.reservation import Reservation, ReservationStatus
from app.schemas.reservation import (
    ReservationAuditRequest,
    ReservationCreateRequest,
    ReservationResponse,
)


def _fill_names(r: Reservation) -> dict:
    resp = ReservationResponse.model_validate(r).model_dump()
    if r.space:
        resp["space_name"] = r.space.name
    if r.seat:
        resp["seat_no"] = r.seat.seat_no
    if r.user:
        resp["user_name"] = r.user.name
    return resp


def _check_conflict(
    db: Session,
    space_id: int,
    seat_id: int | None,
    date: str,
    start_time: str,
    end_time: str,
    exclude_id: int | None = None,
) -> None:
    query = db.query(Reservation).filter(
        Reservation.date == date,
        Reservation.space_id == space_id,
        Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
    )
    if seat_id:
        query = query.filter(Reservation.seat_id == seat_id)
    else:
        query = query.filter(Reservation.seat_id.is_(None))

    if exclude_id:
        query = query.filter(Reservation.id != exclude_id)

    existing = query.all()

    for r in existing:
        if start_time < r.end_time and end_time > r.start_time:
            target = f"座位(ID:{seat_id})" if seat_id else f"区域(ID:{space_id})"
            raise BusinessException(message=f"该时段已被预约（{target}）")


def create_reservation(
    db: Session, data: ReservationCreateRequest, user_id: int
) -> dict:
    space = db.query(Space).filter(Space.id == data.space_id).first()
    if not space:
        raise BusinessException(message="区域不存在")
    if space.status != 1:
        raise BusinessException(message="区域已关闭，无法预约")

    seat_id = data.seat_id
    if seat_id:
        seat = db.query(Seat).filter(Seat.id == seat_id).first()
        if not seat:
            raise BusinessException(message="座位不存在")
        if seat.status != 1:
            raise BusinessException(message="座位已停用，无法预约")
        if seat.space_id != data.space_id:
            raise BusinessException(message="该座位不属于此区域")

    _check_conflict(db, data.space_id, seat_id, data.date, data.start_time, data.end_time)

    reservation = Reservation(
        user_id=user_id,
        space_id=data.space_id,
        seat_id=seat_id,
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
    return PageResponse(list=[_fill_names(r) for r in items], total=total)


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
    return PageResponse(list=[_fill_names(r) for r in items], total=total)


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
            db, r.space_id, r.seat_id, r.date, r.start_time, r.end_time, exclude_id=r.id
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
                _check_conflict(db, r.space_id, r.seat_id, r.date, r.start_time, r.end_time, exclude_id=r.id)
            except BusinessException as e:
                errors.append({"id": rid, "reason": e.message})
                continue
        r.status = status
        r.audit_remark = audit_remark
        success_count += 1
    db.commit()
    return {"success_count": success_count, "errors": errors}