from typing import Literal

from pydantic import BaseModel, ConfigDict


UserRole = Literal["student", "admin"]
UserStatusInt = Literal[0, 1]


class UserCreateRequest(BaseModel):
    username: str
    password: str = "123456"
    name: str
    role: UserRole = "student"
    phone: str | None = None
    email: str | None = None
    avatar: str | None = None
    status: UserStatusInt = 1


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    role: UserRole
    phone: str | None = None
    email: str | None = None
    avatar: str | None = None
    status: UserStatusInt
    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role: UserRole | None = None
    status: UserStatusInt | None = None


class PasswordUpdateRequest(BaseModel):
    old_password: str
    new_password: str