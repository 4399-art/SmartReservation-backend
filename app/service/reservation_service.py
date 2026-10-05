from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.reservation import Reservation, ReservationStatus
from app.model.seat import Seat
from app.model.space import Space
from app.schemas.reservation import (
    ReservationAuditRequest,
    ReservationCreateRequest,
)


def _fill_names(r: Reservation) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "user_name": r.user.username if r.user else "",
        "space_id": r.space_id,
        "space_name": r.space.name if r.space else "",
        "seat_id": r.seat_id,
        "seat_no": r.seat.seat_no if r.seat else None,
        "headcount": r.headcount or 1,
        "date": r.date,
        "start_time": r.start_time,
        "end_time": r.end_time,
        "remark": r.remark,
        "status": r.status,
        "audit_remark": r.audit_remark,
    }


def _time_to_min(t: str) -> int:
    if not t:
        return 0
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1]) if len(parts) > 1 else int(parts[0]) * 60


def _check_capacity(
    db: Session,
    space_id: int,
    date: str,
    start_time: str,
    end_time: str,
    headcount: int,
    exclude_id: int | None = None,
) -> None:
    space = db.query(Space).filter(Space.id == space_id).first()
    if not space:
        raise BusinessException(message="区域不存在")

    capacity = space.capacity
    if headcount > capacity:
        raise BusinessException(message=f"占用名额({headcount}) 超过区域容量({capacity})")

    start_min = _time_to_min(start_time)
    end_min = _time_to_min(end_time)

    existing = (
        db.query(Reservation)
        .filter(
            Reservation.space_id == space_id,
            Reservation.date == date,
            Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
        )
        .all()
    )
    if exclude_id:
        existing = [r for r in existing if r.id != exclude_id]

    critical = set()
    critical.add(start_min)
    critical.add(end_min)
    active_res = []
    for r in existing:
        s = _time_to_min(r.start_time)
        e = _time_to_min(r.end_time)
        if s < end_min and e > start_min:
            critical.add(s)
            critical.add(e)
            active_res.append(r)

    if not active_res:
        return

    max_occupied = 0
    for t in critical:
        if t <= start_min or t >= end_min:
            continue
        occupied = headcount
        for r in active_res:
            if _time_to_min(r.start_time) <= t < _time_to_min(r.end_time):
                occupied += r.headcount or 1
        max_occupied = max(max_occupied, occupied)

    if max_occupied > capacity:
        raise BusinessException(
            message=f"该时段容量不足：该区域容量 {capacity} 人，当前时段最多可承载 {capacity - headcount} 人"
        )


def _check_seat_conflict(
    db: Session,
    space_id: int,
    seat_id: int,
    date: str,
    start_time: str,
    end_time: str,
    exclude_id: int | None = None,
) -> None:
    query = db.query(Reservation).filter(
        Reservation.space_id == space_id,
        Reservation.seat_id == seat_id,
        Reservation.date == date,
        Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
    )
    if exclude_id:
        query = query.filter(Reservation.id != exclude_id)

    for r in query.all():
        if start_time < r.end_time and end_time > r.start_time:
            raise BusinessException(message=f"该时段座位已被占用（{r.start_time}-{r.end_time}）")


def create_reservation(
    db: Session, data: ReservationCreateRequest, user_id: int
) -> dict:
    space = db.query(Space).filter(Space.id == data.space_id).first()
    if not space:
        raise BusinessException(message="区域不存在")
    if space.status != 1:
        raise BusinessException(message="区域已关闭，无法预约")

    seat_id = data.seat_id
    headcount = data.headcount or 1

    if seat_id:
        seat = db.query(Seat).filter(Seat.id == seat_id).first()
        if not seat:
            raise BusinessException(message="座位不存在")
        if seat.status != 1:
            raise BusinessException(message="座位已停用，无法预约")
        if seat.space_id != data.space_id:
            raise BusinessException(message="该座位不属于此区域")
        headcount = 1
        _check_seat_conflict(db, data.space_id, seat_id, data.date, data.start_time, data.end_time)
    else:
        if headcount < 1:
            raise BusinessException(message="占用名额至少为 1")

    _check_capacity(db, data.space_id, data.date, data.start_time, data.end_time, headcount)

    reservation = Reservation(
        user_id=user_id,
        space_id=data.space_id,
        seat_id=seat_id,
        headcount=headcount,
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
        if r.seat_id:
            _check_seat_conflict(
                db, r.space_id, r.seat_id, r.date, r.start_time, r.end_time, exclude_id=r.id
            )
        _check_capacity(
            db, r.space_id, r.date, r.start_time, r.end_time,
            r.headcount or 1, exclude_id=r.id,
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
                if r.seat_id:
                    _check_seat_conflict(
                        db, r.space_id, r.seat_id, r.date, r.start_time, r.end_time, exclude_id=r.id
                    )
                _check_capacity(
                    db, r.space_id, r.date, r.start_time, r.end_time,
                    r.headcount or 1, exclude_id=r.id,
                )
            except BusinessException as e:
                errors.append({"id": rid, "reason": e.message})
                continue
        r.status = status
        r.audit_remark = audit_remark
        success_count += 1
    db.commit()
    return {"success_count": success_count, "errors": errors}
