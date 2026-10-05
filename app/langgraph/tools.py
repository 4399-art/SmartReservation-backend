from datetime import datetime, timedelta

from langchain_core.tools import tool

from app.database import SessionLocal
from app.model.seat import Seat
from app.model.space import Space
from app.model.reservation import Reservation, ReservationStatus
from app.rag.vector_store import get_vector_store


def _db():
    return SessionLocal()


def _status_text(status: int) -> str:
    return {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已取消"}.get(status, "未知")


@tool
def list_spaces(keywords: str | None = None) -> str:
    """列出开放中的图书馆区域，可按名称或位置模糊搜索。keywords 可选。"""
    db = _db()
    try:
        query = db.query(Space).filter(Space.status == 1)
        if keywords:
            like = f"%{keywords}%"
            query = query.filter((Space.name.like(like)) | (Space.location.like(like)))
        items = query.order_by(Space.id.desc()).all()
        if not items:
            return "当前没有开放的区域"
        lines = []
        for sp in items:
            lines.append(
                f"[ID:{sp.id}] {sp.name} | 位置:{sp.location or '-'} | "
                f"座位数:{sp.capacity or '-'} | 开放:{sp.open_time or '-'}~{sp.close_time or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def get_space_detail(space_id: int) -> str:
    """获取指定区域的详细信息，包括该区域下的座位列表。"""
    db = _db()
    try:
        sp = db.query(Space).filter(Space.id == space_id).first()
        if not sp:
            return f"区域 ID:{space_id} 不存在"
        if sp.status != 1:
            return f"区域「{sp.name}」当前已关闭，无法预约"

        seats = db.query(Seat).filter(Seat.space_id == space_id).order_by(Seat.row, Seat.col).all()
        lines = [
            f"【区域】ID:{sp.id} 名称:{sp.name}",
            f"位置:{sp.location or '-'}  总座位:{sp.capacity or len(seats)}  状态:开放",
            f"开放时间:{sp.open_time or '-'} ~ {sp.close_time or '-'}",
            f"简介:{sp.description or '无'}",
        ]
        if seats:
            lines.append("\n【座位列表】")
            for s in seats[:30]:
                tags = []
                if s.has_power: tags.append("电源")
                if s.has_socket: tags.append("USB")
                tag_str = f" [{','.join(tags)}]" if tags else ""
                status_str = "可用" if s.status == 1 else "停用"
                lines.append(
                    f"  [ID:{s.id}] {s.seat_no} | 类型:{s.seat_type or '普通'}{tag_str} | 状态:{status_str}"
                )
            if len(seats) > 30:
                lines.append(f"  ...共 {len(seats)} 个座位，已显示前30个")
        else:
            lines.append("\n该区域暂无座位")
        return "\n".join(lines)
    finally:
        db.close()


@tool
def check_seat_availability(
    space_id: int,
    date: str,
    start_time: str,
    end_time: str,
    seat_id: int | None = None,
) -> str:
    """检查区域或座位在指定日期时间段是否可预约。
    date 格式 YYYY-MM-DD，start_time/end_time 格式 HH:mm。
    seat_id 可选，不传则检查该区域所有座位是否都空闲。
    """
    db = _db()
    try:
        sp = db.query(Space).filter(Space.id == space_id).first()
        if not sp:
            return f"区域 ID:{space_id} 不存在"
        if sp.status != 1:
            return f"区域「{sp.name}」当前已关闭"

        if seat_id:
            seat = db.query(Seat).filter(Seat.id == seat_id).first()
            if not seat:
                return f"座位 ID:{seat_id} 不存在"
            target = f"座位({seat.seat_no} @ {sp.name})"
            eq_filter = Reservation.seat_id == seat_id
        else:
            target = f"区域({sp.name})"
            eq_filter = Reservation.seat_id.is_(None)

        existing = (
            db.query(Reservation)
            .filter(
                Reservation.date == date,
                Reservation.space_id == space_id,
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
            return f"✅ {target} 在 {date} {start_time}~{end_time} 可预约"
        return f"❌ {target} 在 {date} {start_time}~{end_time} 与以下预约冲突:\n" + "\n".join(conflicts)
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
            sp_name = r.space.name if r.space else f"区域ID:{r.space_id}"
            seat_info = f" + 座位:{r.seat.seat_no}" if r.seat else ""
            lines.append(
                f"[预约ID:{r.id}] {r.date} {r.start_time}~{r.end_time} | "
                f"区域:{sp_name}{seat_info} | 状态:{_status_text(r.status)}"
                + (f" | 备注:{r.remark}" if r.remark else "")
                + (f" | 审核备注:{r.audit_remark}" if r.audit_remark else "")
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def create_reservation(
    user_id: int,
    space_id: int,
    date: str,
    start_time: str,
    end_time: str,
    seat_id: int | None = None,
    remark: str | None = None,
) -> str:
    """创建座位预约。参数齐全（space_id/date/start_time/end_time 都有值）时直接调用，
    不要再问用户"确认吗"。date 格式 YYYY-MM-DD，start_time/end_time 格式 HH:mm。
    调用前请先用 check_seat_availability 确认该时段可约。"""
    db = _db()
    try:
        sp = db.query(Space).filter(Space.id == space_id).first()
        if not sp:
            return f"区域 ID:{space_id} 不存在"
        if sp.status != 1:
            return f"区域「{sp.name}」已关闭，无法预约"

        if seat_id:
            seat = db.query(Seat).filter(Seat.id == seat_id).first()
            if not seat:
                return f"座位 ID:{seat_id} 不存在"
            if seat.status != 1:
                return f"座位「{seat.seat_no}」已停用，无法预约"
            if seat.space_id != space_id:
                return f"座位「{seat.seat_no}」不属于区域「{sp.name}」"

        eq_filter = Reservation.seat_id.is_(None)
        if seat_id:
            eq_filter = Reservation.seat_id == seat_id

        existing = (
            db.query(Reservation)
            .filter(
                Reservation.date == date,
                Reservation.space_id == space_id,
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
            space_id=space_id,
            seat_id=seat_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            remark=remark,
            status=ReservationStatus.PENDING,
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)

        seat_str = f" + 座位ID:{seat_id}" if seat_id else ""
        return (
            f"✅ 预约创建成功!\n"
            f"预约ID: {reservation.id}\n"
            f"区域: {sp.name}(ID:{space_id}){seat_str}\n"
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
            sp_name = r.space.name if r.space else f"区域ID:{r.space_id}"
            seat_info = f" 座位:{r.seat.seat_no}" if r.seat else ""
            return (
                f"✅ 已取消预约 ID:{reservation_id}\n"
                f"区域:{sp_name}{seat_info} | 时间:{r.date} {r.start_time}~{r.end_time}"
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
    list_spaces,
    get_space_detail,
    check_seat_availability,
    list_my_reservations,
    create_reservation,
    cancel_reservation,
    rag_search,
    get_date_info,
]