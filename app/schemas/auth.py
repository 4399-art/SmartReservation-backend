from pydantic import BaseModel
from app.schemas.user import UserResponse

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginData(BaseModel):
    token: str
    user: UserResponse

class RegisterRequest(BaseModel):
    username: str
    password: str
