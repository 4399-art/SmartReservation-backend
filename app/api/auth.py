from pydantic import BaseModel

from fastapi import APIRouter, Depends
from app.schemas.auth import LoginRequest
from sqlalchemy.orm import Session
from app.database import get_db
from app.model.user import User, UserStatus
from app.schemas.user import UserResponse
from app.schemas.response import ApiResponse
from app.utils.jwt import create_access_token
from app.utils.password import verify_password

router = APIRouter(prefix="/api/auth", tags=["权限验证"])


class LoginData(BaseModel):
    token: str
    user: UserResponse


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)) -> ApiResponse[LoginData]:
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.password):
        return ApiResponse.unauthorized(message="账号或密码错误")
    if user.status != UserStatus.ACTIVE:
        return ApiResponse.forbidden(message="账号已被禁用")
    token = create_access_token(user.id)
    return ApiResponse.ok(data=LoginData(token=token, user=UserResponse.model_validate(user)))