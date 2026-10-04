from operator import or_

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.lab import Lab
from app.schemas.lab import LabCreateRequest, LabResponse, LabUpdateRequest


def _commit_and_refresh(db: Session, lab: Lab) -> LabResponse:
    db.commit()
    db.refresh(lab)
    return LabResponse.model_validate(lab)


def get_lab_page_list(
    db: Session, page: int, page_size: int, keywords: str | None = None
):
    query = db.query(Lab)
    if keywords:
        query = query.filter(
            or_(Lab.name.ilike(f"%{keywords}%"), Lab.location.ilike(f"%{keywords}%"))
        )
    total = query.count()
    items = (
        query.order_by(Lab.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(
        list=[LabResponse.model_validate(item) for item in items], total=total
    )


def create_lab(db: Session, data: LabCreateRequest) -> LabResponse:
    exist = db.query(Lab).filter(Lab.name == data.name).first()
    if exist:
        raise BusinessException(message="实验室名称已存在")

    lab = Lab(
        name=data.name,
        location=data.location,
        capacity=data.capacity,
        open_time=data.open_time,
        close_time=data.close_time,
        description=data.description,
        img=data.img,
        status=data.status,
    )
    db.add(lab)
    return _commit_and_refresh(db, lab)


def update_lab(db: Session, lab_id: int, data: LabUpdateRequest) -> LabResponse:
    lab = db.query(Lab).filter(Lab.id == lab_id).first()
    if not lab:
        raise BusinessException(message="实验室不存在")

    payload = data.model_dump(exclude_none=True)
    for field, value in payload.items():
        setattr(lab, field, value)

    return _commit_and_refresh(db, lab)


def delete_lab(db: Session, lab_id: int) -> None:
    lab = db.query(Lab).filter(Lab.id == lab_id).first()
    if not lab:
        raise BusinessException(message="实验室不存在")
    db.delete(lab)
    db.commit()


def get_all_labs(db: Session) -> list[LabResponse]:
    items = db.query(Lab).order_by(Lab.id.desc()).all()
    return [LabResponse.model_validate(item) for item in items]


def get_open_labs(db: Session, keywords: str | None = None) -> list[LabResponse]:
    query = db.query(Lab).filter(Lab.status == 1)
    if keywords:
        query = query.filter(
            or_(Lab.name.ilike(f"%{keywords}%"), Lab.location.ilike(f"%{keywords}%"))
        )
    items = query.order_by(Lab.id.desc()).all()
    return [LabResponse.model_validate(item) for item in items]