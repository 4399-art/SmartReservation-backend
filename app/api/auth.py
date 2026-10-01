from fastapi import APIRouter, Depends, status
from app.schemas.auth import LoginRequest, LoginData
from sqlalchemy.orm import Session
from app.database import get_db
from app.model.user import User, UserStatus
from app.common.response import Response
from app.schemas.user import UserResponse
from app.utils.jwt import create_access_token
from app.utils.password import verify_password

router = APIRouter(prefix="/api/auth", tags=["权限验证"])


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)) -> Response:
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.password):
        return Response.error(code=status.HTTP_401_UNAUTHORIZED, message="账号或密码错误")
    if user.status != UserStatus.ACTIVE:
        return Response.error(code=status.HTTP_403_FORBIDDEN, message="账号已被禁用")
    token = create_access_token(user.id)
    return Response.success(data=LoginData(token=token, user=UserResponse.model_validate(user)))