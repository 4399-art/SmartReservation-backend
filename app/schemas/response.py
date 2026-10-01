from typing import Generic, TypeVar

from fastapi import status
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None

    @classmethod
    def ok(cls, data: T | None = None, message: str = "操作成功") -> "ApiResponse[T]":
        return cls(code=status.HTTP_200_OK, message=message, data=data)

    @classmethod
    def fail(cls, message: str) -> "ApiResponse[None]":
        return cls(code=status.HTTP_400_BAD_REQUEST, message=message)

    @classmethod
    def unauthorized(cls, message: str = "请先登录") -> "ApiResponse[None]":
        return cls(code=status.HTTP_401_UNAUTHORIZED, message=message)

    @classmethod
    def forbidden(cls, message: str = "无权访问") -> "ApiResponse[None]":
        return cls(code=status.HTTP_403_FORBIDDEN, message=message)

    @classmethod
    def not_found(cls, message: str = "资源不存在") -> "ApiResponse[None]":
        return cls(code=status.HTTP_404_NOT_FOUND, message=message)

    @classmethod
    def error(cls, message: str = "服务器内部错误") -> "ApiResponse[None]":
        return cls(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=message)