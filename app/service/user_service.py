from sqlalchemy.orm import Session

from app.model.user import User
from app.schemas.user import UserResponse, UserUpdateRequest


def get_user(user_id: int, db: Session) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    return UserResponse.model_validate(user)


def update_user(user_id: int, data: UserUpdateRequest, db: Session) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)