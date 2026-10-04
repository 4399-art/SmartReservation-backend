from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user
from app.model.user import User
from app.schemas.equipment import EquipmentCreateRequest, EquipmentUpdateRequest
from app.service import equipment_service

router = APIRouter(prefix="/equipment", tags=["设备管理"])


@router.get("/list")
def get_equipment_list(
    page: int = 1,
    page_size: int = 10,
    keywords: str | None = None,
    lab_id: int | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = equipment_service.get_equipment_page_list(db, page, page_size, keywords, lab_id)
    return Response.success(data=res)


@router.post("")
def create_equipment(
    data: EquipmentCreateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = equipment_service.create_equipment(db, data)
    return Response.success(data=res)


@router.put("/{equipment_id}")
def update_equipment(
    equipment_id: int,
    data: EquipmentUpdateRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    res = equipment_service.update_equipment(db, equipment_id, data)
    return Response.success(data=res)


@router.delete("/{equipment_id}")
def delete_equipment(
    equipment_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    equipment_service.delete_equipment(db, equipment_id)
    return Response.success(message="删除成功")

@router.get("/lab/{lab_id}")
def get_equipment_by_lab(
    lab_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = equipment_service.get_equipment_by_lab(db, lab_id)
    return Response.success(data=res)

