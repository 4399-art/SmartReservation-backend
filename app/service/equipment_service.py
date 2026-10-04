from operator import or_

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.equipment import Equipment
from app.model.lab import Lab
from app.schemas.equipment import EquipmentCreateRequest, EquipmentResponse, EquipmentUpdateRequest


def _fill_lab_name(item: Equipment) -> dict:
    data = EquipmentResponse.model_validate(item).model_dump()
    if item.lab:
        data["lab_name"] = item.lab.name
    return data


def get_equipment_page_list(
    db: Session, page: int, page_size: int, keywords: str | None = None, lab_id: int | None = None
):
    query = db.query(Equipment).join(Lab, Equipment.lab_id == Lab.id)
    if keywords:
        query = query.filter(
            or_(Equipment.name.ilike(f"%{keywords}%"), Equipment.spec.ilike(f"%{keywords}%"))
        )
    if lab_id:
        query = query.filter(Equipment.lab_id == lab_id)
    total = query.count()
    items = (
        query.order_by(Equipment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(
        list=[_fill_lab_name(item) for item in items], total=total
    )


def create_equipment(db: Session, data: EquipmentCreateRequest) -> dict:
    lab = db.query(Lab).filter(Lab.id == data.lab_id).first()
    if not lab:
        raise BusinessException(message="所属实验室不存在")

    equipment = Equipment(
        lab_id=data.lab_id,
        name=data.name,
        description=data.description,
        img=data.img,
        spec=data.spec,
        quantity=data.quantity,
        status=data.status,
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return _fill_lab_name(equipment)


def update_equipment(db: Session, equipment_id: int, data: EquipmentUpdateRequest) -> dict:
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise BusinessException(message="设备不存在")

    if data.lab_id is not None:
        lab = db.query(Lab).filter(Lab.id == data.lab_id).first()
        if not lab:
            raise BusinessException(message="所属实验室不存在")

    payload = data.model_dump(exclude_none=True)
    for field, value in payload.items():
        setattr(equipment, field, value)

    db.commit()
    db.refresh(equipment)
    return _fill_lab_name(equipment)


def delete_equipment(db: Session, equipment_id: int) -> None:
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise BusinessException(message="设备不存在")
    db.delete(equipment)
    db.commit()

def get_equipment_by_lab(db: Session, lab_id: int) -> list[dict]:
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.status == 1).first()
    if not lab:
        raise BusinessException(message="实验室不存在或已关闭")
    items = (
        db.query(Equipment)
        .filter(Equipment.lab_id == lab_id)
        .order_by(Equipment.id.desc())
        .all()
    )
    return [_fill_lab_name(item) for item in items]
