from datetime import datetime, timedelta

from langchain_core.tools import tool

from app.database import SessionLocal
from app.model.equipment import Equipment
from app.model.lab import Lab
from app.model.reservation import Reservation, ReservationStatus
from app.rag.vector_store import get_vector_store


def _db():
    return SessionLocal()


def _status_text(status: int) -> str:
    return {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已取消"}.get(status, "未知")


@tool
def list_labs(keywords: str | None = None) -> str:
    """列出开放中的实验室，可按名称或位置模糊搜索。keywords 可选。"""
    db = _db()
    try:
        query = db.query(Lab).filter(Lab.status == 1)
        if keywords:
            like = f"%{keywords}%"
            query = query.filter((Lab.name.like(like)) | (Lab.location.like(like)))
        items = query.order_by(Lab.id.desc()).all()
        if not items:
            return "当前没有开放的实验室"
        lines = []
        for lab in items:
            lines.append(
                f"[ID:{lab.id}] {lab.name} | 位置:{lab.location or '-'} | "
                f"容纳:{lab.capacity or '-'}人 | 开放时间:{lab.open_time or '-'}~{lab.close_time or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def get_lab_detail(lab_id: int) -> str:
    """获取指定实验室的详细信息，包括该实验室下的所有设备列表。"""
    db = _db()
    try:
        lab = db.query(Lab).filter(Lab.id == lab_id).first()
        if not lab:
            return f"实验室 ID:{lab_id} 不存在"
        if lab.status != 1:
            return f"实验室「{lab.name}」当前已关闭，无法预约"

        equipments = db.query(Equipment).filter(Equipment.lab_id == lab_id).all()
        lines = [
            f"【实验室】ID:{lab.id} 名称:{lab.name}",
            f"位置:{lab.location or '-'}  容纳:{lab.capacity or '-'}人  状态:开放",
            f"开放时间:{lab.open_time or '-'} ~ {lab.close_time or '-'}",
            f"简介:{lab.description or '无'}",
        ]
        if equipments:
            lines.append("\n【设备列表】")
            for eq in equipments:
                status_str = "正常" if eq.status == 1 else "维修中"
                lines.append(
                    f"  [ID:{eq.id}] {eq.name} | 型号:{eq.spec or '-'} | "
                    f"数量:{eq.quantity} | 状态:{status_str} | 说明:{eq.description or '-'}"
                )
        else:
            lines.append("\n该实验室暂无设备")
        return "\n".join(lines)
    finally:
        db.close()


@tool
def check_availability(
    lab_id: int,
    date: str,
    start_time: str,
    end_time: str,
    equipment_id: int | None = None,
) -> str:
    """检查实验室或设备在指定日期时间段是否可预约。
    date 格式 YYYY-MM-DD，start_time/end_time 格式 HH:mm。
    equipment_id 可选，不传则检查实验室本身。
    """
    db = _db()
    try:
        lab = db.query(Lab).filter(Lab.id == lab_id).first()
        if not lab:
            return f"实验室 ID:{lab_id} 不存在"
        if lab.status != 1:
            return f"实验室「{lab.name}」当前已关闭"

        target = f"实验室({lab.name})"
        eq_filter = Reservation.equipment_id.is_(None)
        if equipment_id:
            eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
            if not eq:
                return f"设备 ID:{equipment_id} 不存在"
            target = f"设备({eq.name} @ {lab.name})"
            eq_filter = Reservation.equipment_id == equipment_id

        existing = (
            db.query(Reservation)
            .filter(
                Reservation.date == date,
                Reservation.lab_id == lab_id,
                eq_filter,
                Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
            )
            .all()
        )

        conflicts = []
        for r in existing:
            if start_time < r.end_time and end_time > r.start_time:
                conflicts.append(f"  {r.start_time}~{r.end_time} (预约ID:{r.id}, 状态:{_status_text(r.status)})")

        if not conflicts:
            return (
                f"✅ {target} 在 {date} {start_time}~{end_time} 可预约"
            )
        return (
            f"❌ {target} 在 {date} {start_time}~{end_time} 与以下预约冲突:\n"
            + "\n".join(conflicts)
        )
    finally:
        db.close()


@tool
def list_my_reservations(user_id: int, status: int | None = None) -> str:
    """查询当前用户的预约记录。status 可选: 0=待审核 1=已通过 2=已拒绝 3=已取消。"""
    db = _db()
    try:
        query = db.query(Reservation).filter(Reservation.user_id == user_id)
        if status is not None:
            query = query.filter(Reservation.status == status)
        items = query.order_by(Reservation.id.desc()).limit(20).all()
        if not items:
            return "暂无预约记录"
        lines = []
        for r in items:
            lab_name = r.lab.name if r.lab else f"ID:{r.lab_id}"
            eq_info = f" + 设备:{r.equipment.name}" if r.equipment else ""
            lines.append(
                f"[预约ID:{r.id}] {r.date} {r.start_time}~{r.end_time} | "
                f"实验室:{lab_name}{eq_info} | 状态:{_status_text(r.status)}"
                + (f" | 备注:{r.remark}" if r.remark else "")
                + (f" | 审核备注:{r.audit_remark}" if r.audit_remark else "")
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def create_reservation(
    user_id: int,
    lab_id: int,
    date: str,
    start_time: str,
    end_time: str,
    equipment_id: int | None = None,
    remark: str | None = None,
) -> str:
    """创建预约。参数齐全（lab_id/date/start_time/end_time 都有值）时直接调用，
    不要再问用户"确认吗"。date 格式 YYYY-MM-DD，start_time/end_time 格式 HH:mm。
    调用前请先用 check_availability 确认该时段可约。"""
    db = _db()
    try:
        lab = db.query(Lab).filter(Lab.id == lab_id).first()
        if not lab:
            return f"实验室 ID:{lab_id} 不存在"
        if lab.status != 1:
            return f"实验室「{lab.name}」已关闭，无法预约"

        if equipment_id:
            eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
            if not eq:
                return f"设备 ID:{equipment_id} 不存在"
            if eq.status != 1:
                return f"设备「{eq.name}」维修中，无法预约"
            if eq.lab_id != lab_id:
                return f"设备「{eq.name}」不属于实验室「{lab.name}」"

        eq_filter = Reservation.equipment_id.is_(None)
        if equipment_id:
            eq_filter = Reservation.equipment_id == equipment_id

        existing = (
            db.query(Reservation)
            .filter(
                Reservation.date == date,
                Reservation.lab_id == lab_id,
                eq_filter,
                Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
            )
            .all()
        )
        for r in existing:
            if start_time < r.end_time and end_time > r.start_time:
                return f"创建失败: {date} {start_time}~{end_time} 时段已被预约(预约ID:{r.id})"

        reservation = Reservation(
            user_id=user_id,
            lab_id=lab_id,
            equipment_id=equipment_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            remark=remark,
            status=ReservationStatus.PENDING,
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)

        eq_str = f" + 设备ID:{equipment_id}" if equipment_id else ""
        return (
            f"✅ 预约创建成功!\n"
            f"预约ID: {reservation.id}\n"
            f"实验室: {lab.name}(ID:{lab_id}){eq_str}\n"
            f"时间: {date} {start_time}~{end_time}\n"
            f"状态: 待审核\n"
            f"请等待管理员审核后生效"
        )
    except Exception as e:
        db.rollback()
        return f"创建预约失败: {e}"
    finally:
        db.close()


@tool
def cancel_reservation(user_id: int, reservation_id: int) -> str:
    """取消自己的预约。待审核或已通过状态的预约可以取消。"""
    db = _db()
    try:
        r = (
            db.query(Reservation)
            .filter(Reservation.id == reservation_id, Reservation.user_id == user_id)
            .first()
        )
        if not r:
            return f"预约 ID:{reservation_id} 不存在或无权操作"
        if r.status in (ReservationStatus.PENDING, ReservationStatus.APPROVED):
            r.status = ReservationStatus.CANCELLED
            db.commit()
            lab_name = r.lab.name if r.lab else f"ID:{r.lab_id}"
            return (
                f"✅ 已取消预约 ID:{reservation_id}\n"
                f"实验室:{lab_name} | 时间:{r.date} {r.start_time}~{r.end_time}"
            )
        if r.status == ReservationStatus.CANCELLED:
            return f"预约 ID:{reservation_id} 已经是取消状态"
        if r.status == ReservationStatus.REJECTED:
            return f"预约 ID:{reservation_id} 已被拒绝，无法取消"
        return f"预约 ID:{reservation_id} 当前状态({_status_text(r.status)})无法取消"
    except Exception as e:
        db.rollback()
        return f"取消预约失败: {e}"
    finally:
        db.close()


@tool
def rag_search(question: str) -> str:
    """从系统知识库中检索相关信息。用于回答关于预约规则、使用说明等文档类问题。"""
    try:
        vector_store = get_vector_store()
        retriever = vector_store.as_retriever(search_kwargs={"k": 4})
        docs = retriever.invoke(question)
        if not docs:
            return "知识库中没有找到相关内容"
        context = "\n\n".join(
            f"[来源:{d.metadata.get('source', '未知')}]\n{d.page_content}"
            for d in docs
        )
        return f"【知识库检索结果】\n{context}"
    except Exception as e:
        return f"知识库检索出错: {e}"


@tool
def get_date_info() -> str:
    """获取当前真实日期和时间信息。凡涉及日期（用户说"明天"、"后天"、"周五"、没说日期等）
    必须先调用此工具拿准确日期，禁止自己编造日期。返回格式: YYYY-MM-DD。"""
    today = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    lines = [
        f"当前时间: {today.strftime('%Y-%m-%d %H:%M')} {weekdays[today.weekday()]}",
        f"今天: {today.strftime('%Y-%m-%d')} {weekdays[today.weekday()]}",
        f"明天: {(today + timedelta(days=1)).strftime('%Y-%m-%d')} {weekdays[(today + timedelta(days=1)).weekday()]}",
        f"后天: {(today + timedelta(days=2)).strftime('%Y-%m-%d')} {weekdays[(today + timedelta(days=2)).weekday()]}",
    ]
    return "\n".join(lines)


ALL_TOOLS = [
    list_labs,
    get_lab_detail,
    check_availability,
    list_my_reservations,
    create_reservation,
    cancel_reservation,
    rag_search,
    get_date_info,
]