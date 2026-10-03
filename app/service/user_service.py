from operator import or_

from fastapi import status
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.model.user import User
from app.schemas.user import UserCreateRequest, UserResponse, UserUpdateRequest, PasswordUpdateRequest
from app.utils.password import verify_password, hash_password


_ALLOWED_SELF_FIELDS = {"name", "email", "phone", "avatar"}
_ADMIN_PROTECTED_FIELDS = {"role", "status"}


def _apply_update(user: User, data: UserUpdateRequest, allowed_fields: set[str]) -> None:
    payload = data.model_dump(exclude_none=True)
    for field, value in payload.items():
        if field not in allowed_fields:
            raise BusinessException(message=f"无权限修改字段: {field}")
        setattr(user, field, value)


def _commit_and_refresh(db: Session, user: User) -> UserResponse:
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


def get_user(user_id: int, db: Session) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    return UserResponse.model_validate(user)


def update_user_info(user_id: int, data: UserUpdateRequest, db: Session) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise BusinessException(message="用户不存在")

    if data.model_dump(exclude_none=True).keys() - _ALLOWED_SELF_FIELDS:
        raise BusinessException(message="只能修改个人资料，不能修改角色或状态")

    _apply_update(user, data, _ALLOWED_SELF_FIELDS)
    return _commit_and_refresh(db, user)


def update_password(user_id: int, data: PasswordUpdateRequest, db: Session) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise BusinessException(message="用户不存在")

    if not verify_password(data.old_password, user.password):
        raise BusinessException(message="旧密码错误", code=status.HTTP_400_BAD_REQUEST)

    user.password = hash_password(data.new_password)
    return _commit_and_refresh(db, user)


def get_user_page_list(
    db: Session, page: int, page_size: int, keywords: str | None = None
):
    query = db.query(User)
    if keywords:
        query = query.filter(
            or_(User.username.ilike(f"%{keywords}%"), User.name.ilike(f"%{keywords}%"))
        )
    total = query.count()
    items = (
        query.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(
        list=[UserResponse.model_validate(item) for item in items], total=total
    )


def create_user(db: Session, data: UserCreateRequest) -> UserResponse:
    exist = db.query(User).filter(User.username == data.username).first()
    if exist:
        raise BusinessException(message="账号已存在")

    user = User(
        username=data.username,
        password=hash_password(data.password),
        name=data.name,
        role=data.role,
        email=data.email,
        phone=data.phone,
        avatar=data.avatar,
        status=data.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


def update_user(db: Session, user_id: int, data: UserUpdateRequest, current_user: User) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise BusinessException(message="用户不存在")

    if data.status == 0 and user_id == current_user.id:
        raise BusinessException(message="不能禁用当前登录的账号")

    _apply_update(user, data, _ALLOWED_SELF_FIELDS | _ADMIN_PROTECTED_FIELDS)
    return _commit_and_refresh(db, user)


def delete_user(db: Session, user_id: int, current_user: User) -> None:
    if user_id == current_user.id:
        raise BusinessException(message="不能删除当前登录的账号")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise BusinessException(message="用户不存在")
    db.delete(user)
    db.commit()