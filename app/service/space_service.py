from operator import or_

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.reservation import Reservation, ReservationStatus
from app.model.space import Space
from app.schemas.space import SpaceCreateRequest, SpaceResponse, SpaceUpdateRequest


def _commit_and_refresh(db: Session, space: Space) -> SpaceResponse:
    db.commit()
    db.refresh(space)
    return SpaceResponse.model_validate(space)


def get_space_page_list(db: Session, page: int, page_size: int, keywords: str | None = None):
    query = db.query(Space)
    if keywords:
        query = query.filter(
            or_(Space.name.ilike(f"%{keywords}%"), Space.location.ilike(f"%{keywords}%"))
        )
    total = query.count()
    items = (
        query.order_by(Space.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(list=[SpaceResponse.model_validate(item) for item in items], total=total)


def create_space(db: Session, data: SpaceCreateRequest) -> SpaceResponse:
    exist = db.query(Space).filter(Space.name == data.name).first()
    if exist:
        raise BusinessException(message="区域名称已存在")

    space = Space(
        name=data.name,
        location=data.location,
        capacity=data.capacity,
        open_time=data.open_time,
        close_time=data.close_time,
        description=data.description,
        img=data.img,
        status=data.status,
    )
    db.add(space)
    return _commit_and_refresh(db, space)


def update_space(db: Session, space_id: int, data: SpaceUpdateRequest) -> SpaceResponse:
    space = db.query(Space).filter(Space.id == space_id).first()
    if not space:
        raise BusinessException(message="区域不存在")

    payload = data.model_dump(exclude_none=True)
    for field, value in payload.items():
        setattr(space, field, value)

    return _commit_and_refresh(db, space)


def delete_space(db: Session, space_id: int) -> None:
    space = db.query(Space).filter(Space.id == space_id).first()
    if not space:
        raise BusinessException(message="区域不存在")
    db.delete(space)
    db.commit()


def get_all_spaces(db: Session) -> list[SpaceResponse]:
    items = db.query(Space).order_by(Space.id.desc()).all()
    return [SpaceResponse.model_validate(item) for item in items]


def get_open_spaces(db: Session, keywords: str | None = None) -> list[SpaceResponse]:
    query = db.query(Space).filter(Space.status == 1)
    if keywords:
        query = query.filter(
            or_(Space.name.ilike(f"%{keywords}%"), Space.location.ilike(f"%{keywords}%"))
        )
    items = query.order_by(Space.id.desc()).all()
    return [SpaceResponse.model_validate(item) for item in items]


def _time_to_min(t: str) -> int:
    if not t:
        return 0
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1]) if len(parts) > 1 else int(parts[0]) * 60


def get_space_occupancy(db: Session, space_id: int, date: str) -> dict:
    space = db.query(Space).filter(Space.id == space_id).first()
    if not space:
        raise BusinessException(message="区域不存在")

    reservations = (
        db.query(Reservation)
        .filter(
            Reservation.space_id == space_id,
            Reservation.date == date,
            Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
        )
        .order_by(Reservation.start_time)
        .all()
    )

    open_min = _time_to_min(space.open_time or "08:00")
    close_min = _time_to_min(space.close_time or "22:00")

    critical = set()
    critical.add(open_min)
    critical.add(close_min)
    for r in reservations:
        critical.add(_time_to_min(r.start_time))
        critical.add(_time_to_min(r.end_time))
    critical = sorted(critical)

    capacity_segments = []
    max_occ = 0
    for i in range(len(critical) - 1):
        t0 = critical[i]
        t1 = critical[i + 1]
        if t0 >= t1 or t0 < open_min or t1 > close_min:
            continue
        occ = 0
        for r in reservations:
            rs = _time_to_min(r.start_time)
            re_ = _time_to_min(r.end_time)
            if rs <= t0 and re_ >= t1:
                occ += r.headcount or 1
        capacity_segments.append(
            {
                "start_min": t0,
                "end_min": t1,
                "occupied": occ,
                "available": max(0, space.capacity - occ),
            }
        )
        max_occ = max(max_occ, occ)

    occupancy = []
    for r in reservations:
        target = "整个区域" if r.seat_id is None else (r.seat.seat_no if r.seat else f"座位ID:{r.seat_id}")
        level = "seat" if r.seat_id else "space"
        occupancy.append(
            {
                "reservation_id": r.id,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "seat_id": r.seat_id,
                "seat_label": target,
                "level": level,
                "headcount": r.headcount or 1,
                "status": r.status,
                "status_text": "待审核" if r.status == ReservationStatus.PENDING else "已通过",
                "user_name": r.user.name if r.user else (r.user.username if r.user else ""),
            }
        )

    return {
        "space_id": space_id,
        "space_name": space.name,
        "date": date,
        "capacity": space.capacity,
        "max_occupied": max_occ,
        "open_time": space.open_time,
        "close_time": space.close_time,
        "occupancy": occupancy,
        "capacity_segments": capacity_segments,
    }
