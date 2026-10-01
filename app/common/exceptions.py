from fastapi import Request, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from app.common.response import Response


class BusinessException(Exception):
    """自定义业务异常：抛出后由全局处理器捕获，返回 HTTP 200 + 业务错误码"""

    def __init__(self, message: str, code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.code = code
        super().__init__(message)


async def business_exception_handler(request: Request, exc: BusinessException):
    """业务异常处理器：HTTP 200，body.code 为业务错误码"""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Response.error(code=exc.code, message=exc.message).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理器：透传状态码"""
    return JSONResponse(
        status_code=exc.status_code,
        content=Response.error(code=exc.status_code, message=str(exc.detail)).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验异常处理器"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=Response.error(code=status.HTTP_422_UNPROCESSABLE_ENTITY, message="请求参数校验错误").model_dump(),
    )


async def global_exception_handler(request: Request, exc: Exception):
    """全局兜底异常处理器：捕获所有未处理的异常，返回 500"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=Response.error(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="服务器内部错误").model_dump(),
    )