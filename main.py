from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import HTTPException, RequestValidationError
from starlette.staticfiles import StaticFiles

from app.model.user import User
from app.database import Base, engine

from fastapi.middleware.cors import CORSMiddleware

from app.common.exceptions import (
    BusinessException,
    business_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)
from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.user import router as user_router
from app.config import settings, UPLOAD_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== 应用启动，初始化数据库表 ===")
    try:
        Base.metadata.create_all(bind=engine)
        print("=== 数据库表初始化完成 ===")
    except Exception as e:
        print(f"=== 数据库连接失败（应用仍会启动）: {e} ===")
    yield
    print("=== 应用关闭 ===")


app = FastAPI(lifespan=lifespan)

app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 挂载静态资源：/uploads/xxx.jpg → uploads/xxx.jpg
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

origins = settings.cors_origins_list

is_wildcard = origins == ["*"]

app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=not is_wildcard,
	allow_methods=["*"],
	allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(files_router)
api_router.include_router(user_router)
app.include_router(api_router)

@app.get("/")
def root():
    return {"Hello": "World"}