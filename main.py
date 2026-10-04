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
from app.api.equipment import router as equipment_router
from app.api.files import router as files_router
from app.api.lab import router as lab_router
from app.api.rag import router as rag_router
from app.api.reservation import router as reservation_router
from app.api.user import router as user_router
from app.config import settings, UPLOAD_DIR

from app.model.equipment import Equipment
from app.model.lab import Lab
from app.model.reservation import Reservation


def _print_banner(db_ok: bool):
    banner = r"""
  ____          _           ____                 _      _____            _             _       
 / ___| __ _ __| |_ __ ___ |  _ \ ___  __ _  ___| |_   | ____|_ __   ___| |_ _ __ __ _| |_ ___ 
 \___ \/ _` / _` | '_ ` _ \| |_) / _ \/ _` |/ __| __|  |  _| | '_ \ / _ \ __| '__/ _` | __/ _ \
  ___) | (_| | (_| | | | | |  _ <  __/ (_| | (__| |_   | |___| | | |  __/ |_| | | (_| | ||  __/
 |____/ \__,_|\__,_|_| |_|_|_| \_\___|\__,_|\___|\__|  |_____|_| |_|\___|\__|_|  \__,_|\__\___|
    """
    print(banner)
    print(f"  服务名称: 智能实验室预约系统")
    print(f"  服务地址: {settings.SERVER_HOST}")
    print(f"  API 前缀: /api")
    print(f"  数据库  : {'✓ 已连接' if db_ok else '✗ 连接失败'}")
    print(f"  静态资源: /uploads")
    print("-" * 64)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_ok = True
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        db_ok = False
        print(f"  [警告] 数据库连接失败（应用仍会启动）: {e}")

    _print_banner(db_ok)
    yield
    print("\n  智能实验室预约系统已关闭  \n")


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
api_router.include_router(lab_router)
api_router.include_router(equipment_router)
api_router.include_router(reservation_router)
api_router.include_router(rag_router)
app.include_router(api_router)

@app.get("/")
def root():
    return {"Hello": "World"}