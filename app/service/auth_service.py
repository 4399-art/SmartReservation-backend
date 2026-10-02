from fastapi import status
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.model.user import User, UserStatus
from app.schemas.auth import LoginData, LoginRequest, RegisterRequest
from app.schemas.user import UserResponse
from app.utils.jwt import create_access_token
from app.utils.password import verify_password, hash_password


def login(data: LoginRequest, db: Session) -> LoginData:
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.password):
        raise BusinessException(
            code=status.HTTP_401_UNAUTHORIZED,
            message="账号或密码错误",
        )

    if user.status != UserStatus.ACTIVE:
        raise BusinessException(
            code=status.HTTP_403_FORBIDDEN,
            message="账号已被禁用",
        )

    token = create_access_token(user.id)
    return LoginData(token=token, user=UserResponse.model_validate(user))

# 注册
def register(data: RegisterRequest, db: Session) -> None:
    # 检查用户名是否存在
    existing_user = db.query(User).filter(User.username == data.username).first()
    if existing_user:
        raise BusinessException(
            code=status.HTTP_400_BAD_REQUEST,
            message="用户名已存在",
        )

    user = User(
        username=data.username,
        password=hash_password(data.password),
        name=data.username,
        role="student",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)