from operator import or_

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
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