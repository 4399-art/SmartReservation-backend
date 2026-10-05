from operator import or_

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.seat import Seat
from app.model.space import Space
from app.schemas.seat import SeatCreateRequest, SeatResponse, SeatUpdateRequest


def _fill_space_name(item: Seat) -> dict:
    data = SeatResponse.model_validate(item).model_dump()
    if item.space:
        data["space_name"] = item.space.name
    return data


def get_seat_page_list(
    db: Session, page: int, page_size: int, keywords: str | None = None, space_id: int | None = None
):
    query = db.query(Seat).join(Space, Seat.space_id == Space.id)
    if keywords:
        query = query.filter(
            or_(Seat.seat_no.ilike(f"%{keywords}%"), Seat.seat_type.ilike(f"%{keywords}%"))
        )
    if space_id:
        query = query.filter(Seat.space_id == space_id)
    total = query.count()
    items = (
        query.order_by(Seat.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(list=[_fill_space_name(item) for item in items], total=total)


def create_seat(db: Session, data: SeatCreateRequest) -> dict:
    space = db.query(Space).filter(Space.id == data.space_id).first()
    if not space:
        raise BusinessException(message="所属区域不存在")

    seat = Seat(
        space_id=data.space_id,
        seat_no=data.seat_no,
        row=data.row,
        col=data.col,
        seat_type=data.seat_type,
        has_power=data.has_power,
        has_socket=data.has_socket,
        description=data.description,
        img=data.img,
        status=data.status,
    )
    db.add(seat)
    db.commit()
    db.refresh(seat)
    return _fill_space_name(seat)


def update_seat(db: Session, seat_id: int, data: SeatUpdateRequest) -> dict:
    seat = db.query(Seat).filter(Seat.id == seat_id).first()
    if not seat:
        raise BusinessException(message="座位不存在")

    if data.space_id is not None:
        space = db.query(Space).filter(Space.id == data.space_id).first()
        if not space:
            raise BusinessException(message="所属区域不存在")

    payload = data.model_dump(exclude_none=True)
    for field, value in payload.items():
        setattr(seat, field, value)

    db.commit()
    db.refresh(seat)
    return _fill_space_name(seat)


def delete_seat(db: Session, seat_id: int) -> None:
    seat = db.query(Seat).filter(Seat.id == seat_id).first()
    if not seat:
        raise BusinessException(message="座位不存在")
    db.delete(seat)
    db.commit()


def get_seats_by_space(db: Session, space_id: int) -> list[dict]:
    space = db.query(Space).filter(Space.id == space_id, Space.status == 1).first()
    if not space:
        raise BusinessException(message="区域不存在或已关闭")
    items = (
        db.query(Seat)
        .filter(Seat.space_id == space_id)
        .order_by(Seat.row, Seat.col, Seat.seat_no)
        .all()
    )
    return [_fill_space_name(item) for item in items]