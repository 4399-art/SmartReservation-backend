# 登录认证机制说明

## 整体架构

认证体系由 4 个文件协作完成：

```
app/
├── api/auth.py           # 登录接口
├── dependencies/auth.py  # Token 校验依赖
├── utils/jwt.py          # JWT 签发与解析
├── config.py             # 密钥等配置（从 .env 读取）
└── .env                  # 环境变量配置
```

## 一、登录流程

```
客户端 POST /api/auth/login { username, password }
        │
        ▼
  1. 查数据库校验用户名 + 密码
  2. 检查用户状态是否为 ACTIVE
  3. 调用 create_access_token(user_id) 生成 JWT
  4. 返回 { code: 200, data: { token, user } }
```

### 关键代码

```python
# app/api/auth.py
@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)) -> ApiResponse[LoginData]:
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.password):
        return ApiResponse.unauthorized(message="账号或密码错误")
    if user.status != UserStatus.ACTIVE:
        return ApiResponse.forbidden(message="账号已被禁用")

    token = create_access_token(user.id)
    return ApiResponse.ok(data=LoginData(token=token, user=UserResponse.model_validate(user)))
```

## 二、JWT 签发

```python
# app/utils/jwt.py
def create_access_token(user_id: int) -> str:
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

| 字段 | 说明 |
|------|------|
| `user_id` | 用户 ID，后续校验时从中提取 |
| `exp` | JWT 标准过期时间字段，当前配置 24 小时 |

### 配置项（.env）

```ini
JWT_SECRET_KEY=hhDFNQEtzk8vNup4NoVGKOJI1qKVT8kvKLLXWhqMQTE
JWT_EXPIRE_HOURS=24
JWT_ALGORITHM=HS256
```

## 三、Token 校验

```python
# app/dependencies/auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_access_token(token)    # 解析 JWT
    user_id = payload.get("user_id")        # 提取用户 ID
    user = db.query(User).filter(User.id == user_id).first()  # 查库
    if user.status != UserStatus.ACTIVE:    # 验证状态
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户已禁用")
    return user
```

### 校验链

```
Authorization: Bearer <token>
        │
        ▼
  1. OAuth2PasswordBearer 提取 token（无 token 则返回 401）
        │
        ▼
  2. decode_access_token 解析 JWT（无效/过期则返回 401）
        │
        ▼
  3. 从 payload 取 user_id（不存在则返回 401）
        │
        ▼
  4. 数据库查询用户（不存在则返回 401）
        │
        ▼
  5. 检查用户状态 != ACTIVE（已禁用则返回 401）
        │
        ▼
  6. 返回 User 对象，注入到路由函数参数
```

## 四、全局认证方案（推荐）

FastAPI 的 `APIRouter` 支持**路由级依赖注入**，一次配置，该 Router 下所有接口自动校验 token，无需每个接口重复写 `Depends(get_current_user)`。

### 核心思路

将公开路由和受保护路由分离到不同的 `APIRouter`：

```
main.py
├── auth_router      → 公开，不需要认证（/api/auth/login）
├── user_router      → 受保护，自动校验 token（/api/users/*）
├── order_router     → 受保护，自动校验 token（/api/orders/*）
└── ...
```

### 1. 公开路由（登录等）

```python
# app/api/auth.py
router = APIRouter(prefix="/api/auth", tags=["权限验证"])  # 不加 dependencies

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    ...
```

### 2. 受保护路由（业务接口）

```python
# app/api/user.py
from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user

router = APIRouter(
    prefix="/api/users",
    tags=["用户管理"],
    dependencies=[Depends(get_current_user)]  # 该文件所有路由自动校验 token
)

@router.get("/me")
def get_me(current_user=Depends(get_current_user)):  # 可省略声明，建议保留以便使用
    return ApiResponse.ok(data=current_user)

@router.get("/list")
def list_users():
    # 即使函数体内用不到 current_user，token 校验也会在进入函数前自动完成
    return ApiResponse.ok(data=[])
```

### 3. 注册到应用

```python
# main.py
from fastapi import FastAPI
from app.dependencies.auth import get_current_user

app = FastAPI()

app.include_router(auth_router)   # 公开路由
app.include_router(user_router)   # 受保护路由，自动校验 token

@app.get("/")
def root():
    return {"Hello": "World"}
```

### 三种方式对比

| 方式 | 写法 | 适用场景 |
|------|------|---------|
| 路由级 | `APIRouter(dependencies=[Depends(get_current_user)])` | **推荐**，该 Router 下全部自动校验 |
| 应用级 | `FastAPI(dependencies=[Depends(...)])` | 全局生效，但登录接口也会被拦截，不灵活 |
| 接口级 | 每个函数加 `Depends(get_current_user)` | 灵活但冗余，适合少量特殊例外 |

### 响应码对照

| 场景 | HTTP 状态码 | body.code |
|------|------------|-----------|
| 登录成功 | 200 | 200 |
| 账号或密码错误 | 200 | 401 |
| 账号已禁用（登录时） | 200 | 403 |
| 无 token / token 无效 | 401 | — |
| 用户已禁用（访问时） | 401 | — |

> 说明：登录接口本身返回 200，通过 body.code 区分业务状态；而 `get_current_user` 依赖中校验失败会直接抛出 HTTP 401，不会进入路由函数体。