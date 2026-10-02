from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.user import UserResponse
from app.service import auth_service
from app.common.response import Response
from app.database import get_db
from app.schemas.auth import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["权限验证"])


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)) -> Response:
    result = auth_service.login(data, db)
    return Response.success(data=result)

# 注册
@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)) -> Response:
    auth_service.register(data, db)
    return Response.success(message="注册成功")
