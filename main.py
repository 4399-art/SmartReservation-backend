from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import HTTPException, RequestValidationError
from starlette.staticfiles import StaticFiles

from app.model.user import User
from app.model.space import Space
from app.model.seat import Seat
from app.model.reservation import Reservation
from app.model.chat_session import ChatSession, ChatMessage

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
from app.api.chat import router as chat_router
from app.api.files import router as files_router
from app.api.space import router as space_router
from app.api.seat import router as seat_router
from app.api.reservation import router as reservation_router
from app.api.rag import router as rag_router
from app.api.user import router as user_router
from app.config import settings, UPLOAD_DIR


def _print_banner(db_ok: bool):
    banner = r"""
  _    _       _           ____  _            _       _            
 | |  | |     | |         |  _ \(_)          | |     | |           
 | |  | |_ __ | |__   ___ | |_) |_  __ _ _ __ | | __ _| |_ ___      
 | |  | | '_ \| '_ \ / _ \|  _ <| |/ _` | '_ \| |/ _` | __/ _ \     
 | |__| | | | | |_) | (_) | |_) | | (_| | |_) | | (_| | ||  __/     
  \____/|_| |_|_.__/ \___/|____/|_|\__,_| .__/|_|\__,_|\__\___|     
                                       | |                         
  ____  _                 ____         |_|                         
 / ___|(_) _____  __ _  / ___|___  _ __ ___  _   _                 
 \___ \| |/ _ \ \/ / _` | |   / _ \| '_ ` _ \| | | |                
  ___) | |  __/>  < (_| | |__| (_) | | | | | | |_| |               
 |____/|_|\___/_/\_\__,_|\____\___/|_| |_| |_|\__,_|               
    """
    print(banner)
    print(f"  服务名称: 智慧图书馆座位预约系统")
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
    print("\n  智慧图书馆座位预约系统已关闭  \n")


app = FastAPI(lifespan=lifespan)

app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

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
api_router.include_router(chat_router)
api_router.include_router(files_router)
api_router.include_router(user_router)
api_router.include_router(space_router)
api_router.include_router(seat_router)
api_router.include_router(reservation_router)
api_router.include_router(rag_router)
app.include_router(api_router)

@app.get("/")
def root():
    return {"service": "智慧图书馆座位预约系统", "status": "ok"}