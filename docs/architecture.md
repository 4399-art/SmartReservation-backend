

# 智能实验室预约系统 — 技术架构与代码精讲

## 一、整体框架

```
SmartReservation/
├── backend/                 # FastAPI + SQLAlchemy 2.0
│   ├── app/
│   │   ├── api/             # 路由控制器层
│   │   ├── common/          # 统一响应、异常处理器
│   │   ├── config.py        # 配置（.env 自动加载）
│   │   ├── database.py      # 数据库引擎 + 会话 + Base 模型
│   │   ├── dependencies/    # 权限依赖（get_current_user / get_current_admin）
│   │   ├── model/           # SQLAlchemy ORM 模型
│   │   ├── schemas/         # Pydantic 请求/响应 DTO
│   │   ├── service/         # 业务逻辑层
│   │   └── utils/           # JWT、密码工具
│   ├── main.py              # 应用入口（lifespan、CORS、路由注册）
│   ├── pyproject.toml       # 依赖声明（FastAPI 0.115 / Python 3.13）
│   └── .env                 # 数据库、JWT 密钥、跨域
│
└── frontend/                # Vue 3 + Vite + Element Plus
    ├── src/
    │   ├── api/             # axios 封装的各模块 API
    │   ├── layouts/         # Layout.vue（顶栏 + 侧栏 + 主体）
    │   ├── router/          # vue-router 配置 + 路由守卫
    │   ├── utils/           # request.js / auth.js / user.js
    │   ├── views/           # 业务页面
    │   └── main.js          # 应用入口
    ├── vite.config.js       # 别名 @ → src
    └── .env                 # VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 技术栈速览

| 层 | 技术 | 版本 |
|----|------|------|
| 后端框架 | FastAPI | 0.115 |
| ORM | SQLAlchemy | 2.0 |
| 数据校验 | Pydantic | 2.10 |
| 数据库 | MySQL (PyMySQL) | 8.x |
| 认证 | JWT (PyJWT) | - |
| 密码加密 | bcrypt | 5.x |
| 前端框架 | Vue | 3.x |
| UI 组件库 | Element Plus | - |
| 构建工具 | Vite | 7.x |
| HTTP 客户端 | axios | - |

---

## 二、数据库模型与表关系

### 表结构一览

```sql
users (用户表)
├── id / create_time / update_time
├── username (唯一) / password (bcrypt)
├── name / role (admin | student) / email / phone
├── status (1 正常 / 0 禁用)
└── avatar / bio / gender

labs (实验室表)
├── id / create_time / update_time
├── name (唯一) / location / capacity
├── open_time / close_time     -- "08:00" / "20:00"
├── description / img
└── status (1 开放 / 0 关闭)

equipments (设备表)
├── id / create_time / update_time
├── lab_id          -- FK → labs.id
├── name / spec / quantity
├── description
└── status (1 正常 / 0 维修中)

reservations (预约表)
├── id / create_time / update_time
├── user_id         -- FK → users.id
├── lab_id          -- FK → labs.id
├── equipment_id    -- FK → equipments.id, NULL 表示仅约实验室
├── date / start_time / end_time   -- 字符串, 如 "2026-10-05" / "09:00"
├── remark / audit_remark
└── status (0 待审核 / 1 已通过 / 2 已拒绝 / 3 已取消)
```

### 关系图

```
users │── 1:N ── reservations ── N:1 ── labs
                  │
                  └── N:1 (可空) ── equipments ── N:1 ── labs
```

一个实验室有多台设备（强制 lab_id），一个预约可只约实验室，也可同时约某台设备。

### Base 模型抽公共字段

所有 ORM 模型继承自 `app/database.py` 中的 `Base`：

```python
class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    create_time: Mapped[datetime] = mapped_column(default=datetime.now)
    update_time: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now
    )
```

好处：每次新表自动有 3 个时间字段，`onupdate=datetime.now` 让 SQLAlchemy 在 `commit()` 前自动刷新。

---

## 三、后端架构精讲

### 3.1 分层职责

```
  请求 → api/ (路由) → service/ (业务) → model/ (数据库) → MySQL
           ↓                ↓
        schemas/          dependencies/
        (校验)            (权限)
           ↓
        common/response.py / common/exceptions.py
        (统一响应 + 全局异常)
```

- **api/** —— 只做 3 件事：参数绑定、调用 service、返回 Response。**不含任何业务判断**。
- **service/** —— 全部业务逻辑在此：校验、冲突检测、状态流转、数据库操作。
- **model/** —— ORM 声明，纯结构。
- **schemas/** —— Pydantic DTO，定义请求体和响应体的形状。
- **dependencies/** —— FastAPI 的 `Depends` 依赖：`get_current_user` 解析 JWT，`get_current_admin` 在其基础上再加 role 检查。

### 3.2 统一响应与异常处理

所有 API 都返回同一种 JSON 外壳：

```json
{"code": 200, "message": "操作成功", "data": {...}}
```

`app/common/response.py`：

```python
class Response(BaseModel):
    code: int
    message: str
    data: Any = None

    @classmethod
    def success(cls, message="操作成功", data=None): ...

    @classmethod
    def error(cls, code=500, message="服务器内部错误"): ...
```

分页则用 `PageResponse`：

```python
class PageResponse(BaseModel):
    list: Any = []
    total: int = 0
```

四种异常 → 四种全局处理器，全部在 `main.py` 注册：

| 异常 | HTTP 状态码 | 说明 |
|------|------------|------|
| `BusinessException` | **200** | 业务错误（如名称重复、时段冲突），前端看 `code` |
| `HTTPException` | 原样透传 | 401 / 403 |
| `RequestValidationError` | 422 | 参数校验失败 |
| `Exception` | 500 | 兜底 |

**核心设计**：业务异常返回 `HTTP 200 + code=400` 而不是 HTTP 400。这样前端 axios 拦截器只需要判断 `code !== 200`，不用同时处理 HTTP 非 2xx 分支。

### 3.3 认证机制

#### 登录流程

```
POST /api/auth/login
  → bcrypt 校验密码
  → jwt.encode({"user_id": user.id}, SECRET, "HS256")
  → 返回 {"token": "eyJ...", "user": {...}}
```

JWT payload 只放 `user_id`（避免大 payload），不放角色等会变的字段。客户端拿到 token 放 localStorage。

#### 请求鉴权（FastAPI Depends 魔法）

```python
# app/dependencies/auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    user_id = payload["user_id"]
    user = db.query(User).filter(User.id == user_id).first()
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(401, "用户已禁用")
    return user

def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise BusinessException(message="无权限访问", code=403)
    return current_user
```

在路由里一行搞定：

```python
@router.get("/my")
def get_my_reservations(
    current_user: User = Depends(get_current_user),   # 任意登录用户
    db: Session = Depends(get_db),
): ...

@router.get("/list")
def get_all_reservations(
    current_user: User = Depends(get_current_admin),  # 只有管理员
    db: Session = Depends(get_db),
): ...
```

#### 自动注入请求头

FastAPI 的 `OAuth2PasswordBearer` 会自动从 `Authorization: Bearer xxx` 头中提取 token，我们在前端 request.js 的请求拦截器里保证每次都带上它。

### 3.4 典型 Service 精讲 —— 预约模块

#### 预约创建：4 层校验

```python
def create_reservation(db, data, user_id):
    # 1. 实验室存在 + 状态为开放
    lab = db.query(Lab).filter(Lab.id == data.lab_id).first()
    if not lab: raise BusinessException("实验室不存在")
    if lab.status != 1: raise BusinessException("实验室已关闭，无法预约")

    # 2. 设备存在 + 正常 + 属于该实验室（如果带了 equipment_id）
    if data.equipment_id:
        eq = db.query(Equipment).filter(Equipment.id == data.equipment_id).first()
        if not eq: raise BusinessException("设备不存在")
        if eq.status != 1: raise BusinessException("设备维修中，无法预约")
        if eq.lab_id != data.lab_id: raise BusinessException("该设备不属于此实验室")

    # 3. 时段冲突检测
    _check_conflict(db, data.lab_id, data.equipment_id, data.date, ...)

    # 4. 写入
    reservation = Reservation(user_id=user_id, ...)
    db.add(reservation); db.commit(); db.refresh(reservation)
    return _fill_names(reservation)
```

`_check_conflict` 的核心是区间重叠判定：

```python
if start_time < r.end_time and end_time > r.start_time:
    raise BusinessException("该时段已被预约")
```

**关键点**：只与 `status ∈ {待审核, 已通过}` 的记录比（已拒绝/已取消的不计）。

#### 审核通过的二次冲突校验

```python
def audit_reservation(db, reservation_id, data):
    ...
    if data.status == ReservationStatus.APPROVED:
        _check_conflict(db, r.lab_id, r.equipment_id, r.date, ..., exclude_id=r.id)
    ...
```

为什么需要？用户 A 提交待审核（status=0），用户 B 同时提交重叠时段（此时 A 还是 0，不冲突）。管理员先过 A，再过 B 时 B 会撞 A 的已通过记录 —— 这时拦截。

`exclude_id=r.id` 是防止自己撞自己。

#### 批量审核：逐条容错

```python
def batch_audit_reservations(db, ids, status, audit_remark):
    errors = []
    for rid in ids:
        r = db.query(...).filter(Reservation.id == rid).first()
        if not r: errors.append({...}); continue
        if r.status not in (...): errors.append({...}); continue
        if status == APPROVED:
            try: _check_conflict(...)
            except BusinessException as e:
                errors.append({...}); continue
        r.status = status; success_count += 1
    db.commit()   # 统一提交
    return {"success_count": success_count, "errors": errors}
```

设计：**部分失败不影响整体**。成功的统一 commit，失败的收集原因返回前端，前端 toast 分开提示。

### 3.5 统一启动入口 —— main.py Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)   # 自动建表
    _print_banner(db_ok)
    yield
    print("系统已关闭")
```

`lifespan` 在 FastAPI 启动前执行。`create_all` 会扫描所有已 import 的 model 并在 MySQL 中 `CREATE TABLE IF NOT EXISTS`，所以新增 model 只要在 main.py 里 import 一次即可，不用手写 SQL。

---

## 四、前端架构精讲

### 4.1 目录结构

```
frontend/src/
├── api/              # 各模块 HTTP 方法
│   ├── auth.js       login / register / changePassword
│   ├── user.js       CRUD + 分页
│   ├── lab.js        CRUD + 分页 + getOpenLabs
│   ├── equipment.js  CRUD + 分页 + getAllLabs + getEquipmentByLab
│   ├── reservation.js  create / my / cancel / audit / batchAudit
│   └── file.js       upload
├── layouts/Layout.vue   # 顶栏 + 侧栏（角色动态菜单）+ router-view
├── router/index.js      # 路由 + beforeEach 守卫
├── utils/
│   ├── request.js    axios 实例 + 请求/响应拦截器
│   ├── auth.js       localStorage token / userInfo
│   └── user.js       Composition API 包装 useUser()
├── views/
│   ├── Login.vue / Register.vue
│   ├── Home.vue / Profile.vue / Password.vue
│   ├── User.vue       管理员 CRUD
│   ├── Lab.vue        同一页面，根据 role 显示两套 UI
│   ├── Equ.vue        管理员 CRUD
│   ├── MyReservation.vue   学生：我的预约
│   └── ResAudit.vue       管理员：预约审核
└── main.js            createApp + ElementPlus + router
```

### 4.2 axios 封装与拦截器

```javascript
// utils/request.js
const service = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL,   // http://127.0.0.1:8000
    timeout: 30000
})

service.interceptors.request.use((config) => {
    const token = getToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

service.interceptors.response.use((res) => {
    const data = res.data
    if (data.code !== 200) {
        ElMessage.error(data.message || '请求失败')
        if (data.code === 401) { logout(); router.push('/login') }
    }
    return data   // 直接返回 { code, message, data }
})
```

**关键**：响应拦截器**不 return res.data** 而是 return `data`（已是对象）。这让业务层可以直接写：

```javascript
const res = await getLabPageList(params)
if (res.code === 200) { ... }
```

而不是 `res.data.code`。

401 统一处理：清 localStorage + 跳登录页，所有页面自动生效。

### 4.3 路由守卫

```javascript
router.beforeEach((to, from) => {
  const token = getToken()
  if (to.path === '/login' || to.path === '/register') return true
  return token ? true : '/login'
})
```

只有 2 个公开页面，其他全部拦截。角色不在这里拦，而是在 Layout.vue 侧栏 + 后端接口层双重保证。

### 4.4 角色驱动 UI

Layout.vue 核心逻辑：

```html
<el-menu-item v-if="userInfo?.role === 'student'" index="/manager/my-reservation">
  我的预约
</el-menu-item>
<el-menu-item v-if="userInfo?.role === 'admin'" index="/manager/res-audit">
  预约审核
</el-menu-item>
```

Lab.vue 更彻底 —— **同一个路由 /manager/lab 根据 role 显示两套完全不同的 UI**：

```vue
<template v-if="isAdmin">
  <!-- 管理员：表格 + 新增/编辑/删除 -->
</template>
<template v-else>
  <!-- 学生：卡片网格 + 查看设备 + 预约弹窗 -->
</template>
```

后端再加一层 `get_current_admin` 依赖兜底，学生就算绕过前端直接调管理员接口也会被拒。

### 4.5 API 函数模板

每个 API 文件结构一致：

```javascript
// api/lab.js
import request from '@/utils/request'

export function getLabPageList(params) {
    return request({ url: '/api/lab/list', method: 'get', params })
}
export function createLabApi(data) {
    return request({ url: '/api/lab', method: 'post', data })
}
export function updateLabApi(id, data) {
    return request({ url: `/api/lab/${id}`, method: 'put', data })
}
export function deleteLabApi(id) {
    return request({ url: `/api/lab/${id}`, method: 'delete' })
}
export function getOpenLabs(params) {
    return request({ url: '/api/lab/all-open', method: 'get', params })
}
```

### 4.6 Element Plus 通用模式

表格+分页几乎每个 CRUD 页面都长这样：

```vue
<el-table :data="tableData" v-loading="loading"
          :header-cell-style="{ backgroundColor: '#f5f7fa', color: '#333' }">
  <!-- 列定义 -->
</el-table>
<el-pagination
    v-model:current-page="params.page"
    v-model:page-size="params.page_size"
    :total="total"
    background
    layout="total, prev, pager, next"
    @current-change="load"
/>
```

新增/编辑弹窗模式：

```vue
<el-dialog v-model="dialogVisible" :title="form.id ? '编辑' : '新增'">
  <el-form ref="formRef" :rules="rules" :model="form" label-width="100px">
    <el-form-item label="名称" prop="name">
      <el-input v-model="form.name" />
    </el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="dialogVisible = false">取消</el-button>
    <el-button type="primary" :loading="loading" @click="handleSave">确定</el-button>
  </template>
</el-dialog>
```

---

## 五、完整接口清单

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 token |
| POST | `/api/auth/register` | 注册 |
| PUT | `/api/auth/password` | 修改密码 |

### 用户（管理员 CRUD）
| 方法 | 路径 | 权限 |
|------|------|------|
| GET | `/api/user/list` | admin |
| POST | `/api/user` | admin |
| PUT | `/api/user/{id}` | admin |
| DELETE | `/api/user/{id}` | admin |
| GET | `/api/user/profile` | 本人 |
| PUT | `/api/user/profile` | 本人 |

### 实验室
| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/lab/list` | admin | 分页 CRUD |
| POST | `/api/lab` | admin | |
| PUT | `/api/lab/{id}` | admin | |
| DELETE | `/api/lab/{id}` | admin | |
| GET | `/api/lab/all` | admin | 下拉框全部 |
| GET | `/api/lab/all-open` | 任意登录 | **学生端开放列表** |

### 设备
| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/equipment/list` | admin | 分页 CRUD（join lab 填 lab_name） |
| POST | `/api/equipment` | admin | |
| PUT | `/api/equipment/{id}` | admin | |
| DELETE | `/api/equipment/{id}` | admin | |
| GET | `/api/equipment/lab/{id}` | 任意登录 | **学生端查看某实验室设备** |

### 预约
| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/reservation` | 任意登录 | 学生提交预约（user_id 后端取） |
| GET | `/api/reservation/my` | 任意登录 | 我的预约 |
| PUT | `/api/reservation/{id}/cancel` | 预约人本人 | 取消 |
| GET | `/api/reservation/list` | admin | 全部预约列表 |
| PUT | `/api/reservation/{id}/audit` | admin | 单条审核 |
| PUT | `/api/reservation/batch-audit` | admin | 批量审核 |

### 文件
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/files/upload` | 上传 → 存 uploads/ → 返回 URL |

---

## 六、权限模型总结

```
                    游客
                      │ 登录后
                 ┌────┴────┐
                 │         │
              学生        管理员
                 │         │
  ┌──────────────┼─────────┼──────────────┐
  │              │         │              │
  ▼              ▼         ▼              ▼
  实验室列表  查看设备    实验室 CRUD    用户 CRUD
  预约提交    我的预约    设备 CRUD      预约审核
  取消预约               预约审核
```

权限靠 **两道闸**：

1. **前端 UI 层**：`v-if="userInfo?.role === 'admin'"` 控制菜单显隐
2. **后端接口层**：`Depends(get_current_user)` / `Depends(get_current_admin)` 强制校验

两道闸互相独立，学生即使绕过前端直接请求管理员接口，后端也会返回 403。

---

## 七、启动指南

### 后端

```bash
# 1. 创建 MySQL 数据库
mysql -u root -p123456 -e "CREATE DATABASE lab_agent CHARACTER SET utf8mb4;"

# 2. 修改 backend/.env 里的 DATABASE_URL
#    DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/lab_agent

# 3. 安装依赖（uv）
cd backend
uv sync

# 4. 启动
uvicorn main:app --reload --port 8000
```

首次启动 `Base.metadata.create_all` 会自动建表。

### 前端

```bash
cd frontend
npm install
npm run dev
# 默认 http://localhost:5173
```

### 预置账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | 123456 | 管理员 |
| student | 123456 | 学生 |

---

## 八、关键设计模式回顾

| 模式 | 位置 | 解决了什么 |
|------|------|-----------|
| Base 模型抽公共字段 | `database.py` | 所有表自动有 id/create_time/update_time |
| Depends 链式复用 | `dependencies/auth.py` | `get_current_admin` 调 `get_current_user`，避免重复解析 JWT |
| Response 包装 + 全局异常 | `common/response.py` + `common/exceptions.py` | 前端只关心 `code !== 200`，不用分 HTTP 状态码 |
| BusinessException → HTTP 200 | `exceptions.py` | 业务错误和系统错误分开，前端拦截器逻辑极简 |
| Lifespan + create_all | `main.py` | 零 SQL 建表，新增 model 只要 import 一次 |
| role 驱动 UI + 后端兜底 | Layout.vue + Depends | 前端隐藏 + 后端拒绝双保险 |
| 时段区间重叠检测 | `reservation_service._check_conflict` | `A.start < B.end and A.end > B.start` 判断任意重叠 |
| 批量审核逐条容错 | `batch_audit_reservations` | 部分成功部分失败，收集错误逐条返回 |
| 同路由多套 UI | Lab.vue | `/manager/lab` 按 role 决定是 CRUD 表格还是卡片网格 |

