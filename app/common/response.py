from typing import Any

from fastapi import status
from pydantic import BaseModel


class Response(BaseModel):
    """统一封装的返回格式"""

    code: int
    message: str
    data: Any = None

    @classmethod
    def success(cls, message: str = "操作成功", data: Any = None):
        return cls(code=status.HTTP_200_OK, message=message, data=data)

    @classmethod
    def error(cls, code: int = status.HTTP_500_INTERNAL_SERVER_ERROR, message: str = "服务器内部错误"):
        return cls(code=code, message=message)