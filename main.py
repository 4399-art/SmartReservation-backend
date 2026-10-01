from fastapi import FastAPI
from fastapi.exceptions import HTTPException, RequestValidationError

from app.model.user import User
from app.database import Base, engine
from app.common.exceptions import (
    BusinessException,
    business_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)
from app.api.auth import router as auth_router

app = FastAPI()

# 注册全局异常处理器
app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(auth_router)

Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"Hello": "World"}