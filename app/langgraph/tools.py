"""LangGraph 工具函数 — 容量感知 + headcount + 智能时段建议"""
import contextlib
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.model.reservation import Reservation, ReservationStatus
from app.model.seat import Seat
from app.model.space import Space
from langchain_core.tools import tool


def _db():
    return SessionLocal()


def _status_text(s: int) -> str:
    return {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已取消"}.get(s, f"未知({s})")


def _time_to_min(t: str) -> int:
    if not t:
        return 0
    parts = t.split(":")
    return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)


def _min_to_time(m: int) -> str:
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def _compute_capacity_segments(db, space_id: int, date: str):
    """计算某区域某天的容量分段 — 返回 [(start_min, end_min, occupied, available, reservations_in_seg)]"""
    sp = db.query(Space).filter(Space.id == space_id).first()
    if not sp:
        return [], 0, 0, 0
    reservations = (
        db.query(Reservation)
        .filter(
            Reservation.space_id == space_id,
            Reservation.date == date,
            Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
        )
        .all()
    )
    open_min = _time_to_min(sp.open_time or "08:00")
    close_min = _time_to_min(sp.close_time or "22:00")

    critical = {open_min, close_min}
    for r in reservations:
        critical.add(_time_to_min(r.start_time))
        critical.add(_time_to_min(r.end_time))
    critical = sorted(critical)

    segments = []
    max_occ = 0
    for i in range(len(critical) - 1):
        t0 = critical[i]
        t1 = critical[i + 1]
        if t0 >= t1 or t0 < open_min or t1 > close_min:
            continue
        occ = 0
        active = []
        for r in reservations:
            rs = _time_to_min(r.start_time)
            re_ = _time_to_min(r.end_time)
            if rs <= t0 and re_ >= t1:
                occ += r.headcount or 1
                active.append(r)
        segments.append((t0, t1, occ, sp.capacity - occ, active))
        max_occ = max(max_occ, occ)

    return segments, open_min, close_min, sp.capacity


def _format_conflict_segment(t0, t1, reservations_in_seg):
    """格式化冲突段里的预约明细"""
    details = []
    seen_ids = set()
    for r in reservations_in_seg:
        if r.id in seen_ids:
            continue
        seen_ids.add(r.id)
        if r.seat_id:
            label = f"座位:{r.seat.seat_no}" if r.seat else f"座位ID:{r.seat_id}"
        else:
            label = f"区域级(×{r.headcount or 1}人)"
        details.append(
            f"    - {r.start_time}~{r.end_time} {label} by {r.user.username if r.user else '?'} "
            f"[{_status_text(r.status)}]"
        )
    return details


def _suggest_free_slots(segments, open_min, close_min, capacity, want_minutes=60, want_headcount=1):
    """从容量分段里找连续可用的时段建议"""
    suggestions = []
    current_run = None  # (start_min, end_min, min_available)
    for t0, t1, occ, avail, _ in segments:
        can_fit = avail >= want_headcount
        if can_fit:
            if current_run is None:
                current_run = [t0, t1, avail]
            else:
                if t0 == current_run[1] and avail >= want_headcount:
                    current_run[1] = t1
                    current_run[2] = min(current_run[2], avail)
                else:
                    # close and emit current_run
                    if current_run[1] - current_run[0] >= want_minutes:
                        suggestions.append(tuple(current_run))
                    current_run = [t0, t1, avail]
        else:
            if current_run and current_run[1] - current_run[0] >= want_minutes:
                suggestions.append(tuple(current_run))
            current_run = None
    if current_run and current_run[1] - current_run[0] >= want_minutes:
        suggestions.append(tuple(current_run))
    return suggestions


# ──────────────────────────────────────────────
#  Tools
# ──────────────────────────────────────────────

@tool
def list_spaces(keywords: str | None = None) -> str:
    """列出所有开放的图书馆区域。可按关键词（区域名/位置）搜索。"""
    db = _db()
    try:
        q = db.query(Space).filter(Space.status == 1)
        if keywords:
            q = q.filter(
                (Space.name.contains(keywords)) | (Space.location.contains(keywords))
            )
        items = q.order_by(Space.id.asc()).all()
        if not items:
            return "当前没有开放的区域"
        lines = ["【开放区域列表】"]
        for sp in items:
            lines.append(
                f"  [ID:{sp.id}] {sp.name} | 位置:{sp.location or '-'} | "
                f"容量:{sp.capacity}人 | 开放:{sp.open_time or '-'}~{sp.close_time or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def get_space_detail(space_id: int) -> str:
    """获取某个区域的详细信息和座位列表。"""
    db = _db()
    try:
        sp = db.query(Space).filter(Space.id == space_id).first()
        if not sp:
            return f"区域 ID:{space_id} 不存在"
        if sp.status != 1:
            return f"区域「{sp.name}」当前已关闭"
        seats = db.query(Seat).filter(Seat.space_id == space_id).order_by(Seat.row, Seat.col).all()
        lines = [
            f"【区域详情】",
            f"ID:{sp.id} 名称:{sp.name}",
            f"位置:{sp.location or '-'}  总容量:{sp.capacity}人  状态:开放",
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
                lines.append(f"  ...共 {len(seats)} 个座位")
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
    headcount: int = 1,
    seat_id: int | None = None,
) -> str:
    """检查区域或座位在指定日期时间段是否可预约。
    date 格式 YYYY-MM-DD，start_time/end_time 格式 HH:mm。
    - seat_id 不传：检查整个区域的容量是否够 headcount 人（默认1）
    - seat_id 传了：检查具体座位是否空闲（此时 headcount 忽略，固定1）
    返回: ✅可预约 / ❌冲突明细 / 💡建议时段。
    """
    db = _db()
    try:
        sp = db.query(Space).filter(Space.id == space_id).first()
        if not sp:
            return f"区域 ID:{space_id} 不存在"
        if sp.status != 1:
            return f"区域「{sp.name}」当前已关闭"

        start_min = _time_to_min(start_time)
        end_min = _time_to_min(end_time)
        open_min = _time_to_min(sp.open_time or "08:00")
        close_min = _time_to_min(sp.close_time or "22:00")

        if start_min < open_min or end_min > close_min:
            return (
                f"❌ 不在开放时间内。区域「{sp.name}」开放时间 {sp.open_time}~{sp.close_time}，"
                f"您要的 {start_time}~{end_time} 超出范围"
            )
        if start_min >= end_min:
            return "❌ 结束时间必须晚于开始时间"

        if seat_id:
            seat = db.query(Seat).filter(Seat.id == seat_id).first()
            if not seat:
                return f"座位 ID:{seat_id} 不存在"
            if seat.status != 1:
                return f"座位「{seat.seat_no}」已停用"
            target = f"座位({seat.seat_no} @ {sp.name})"
            conflicts = (
                db.query(Reservation)
                .filter(
                    Reservation.space_id == space_id,
                    Reservation.seat_id == seat_id,
                    Reservation.date == date,
                    Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
                )
                .all()
            )
            overlap = [
                f"  {r.start_time}~{r.end_time} (预约ID:{r.id}, {_status_text(r.status)})"
                for r in conflicts
                if start_time < r.end_time and end_time > r.start_time
            ]
            if not overlap:
                return f"✅ {target} 在 {date} {start_time}~{end_time} 可预约"
            return f"❌ {target} 在 {date} {start_time}~{end_time} 冲突:\n" + "\n".join(overlap)

        # ── 区域级容量检查 ──
        segments, _, _, _ = _compute_capacity_segments(db, space_id, date)
        cap_conflicts = []
        global_max_occ = 0
        for t0, t1, occ, avail, active in segments:
            if t0 < end_min and t1 > start_min:
                global_max_occ = max(global_max_occ, occ)
                if occ + headcount > sp.capacity:
                    cap_conflicts.append((t0, t1, occ, active))

        if not cap_conflicts:
            final_occ = global_max_occ + headcount
            return (
                f"✅ 区域「{sp.name}」(容量{sp.capacity}人) 在 {date} {start_time}~{end_time} "
                f"可预约 {headcount} 人。\n"
                f"   当前时段已占用 {global_max_occ} 人，预约后将占 {final_occ}/{sp.capacity}"
            )

        # 有冲突 — 返回冲突明细 + 智能建议
        conflict_lines = []
        for t0, t1, occ, active in cap_conflicts:
            conflict_lines.append(f"  {_min_to_time(t0)}~{_min_to_time(t1)} 已占 {occ}/{sp.capacity}:")
            conflict_lines.extend(_format_conflict_segment(t0, t1, active))

        # 找建议
        suggestions = _suggest_free_slots(
            segments, open_min, close_min, sp.capacity,
            want_minutes=min(max(30, end_min - start_min), 120),
            want_headcount=1,
        )
        suggest_lines = []
        for s_start, s_end, s_avail in suggestions[:3]:
            suggest_lines.append(
                f"  ✨ {_min_to_time(s_start)}~{_min_to_time(s_end)} (余量 {s_avail}/{sp.capacity}，"
                f"最多可约 {s_avail} 人)"
            )

        result = (
            f"❌ 区域「{sp.name}」在 {date} {start_time}~{end_time} 容量不足:\n"
            + "\n".join(conflict_lines)
        )
        if suggest_lines:
            result += f"\n\n💡 同天可约时段建议:\n" + "\n".join(suggest_lines)
            result += f"\n直接说时间（如「{_min_to_time(suggestions[0][0])}-{_min_to_time(suggestions[0][1])}」）我马上帮你约"
        return result
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
        lines = ["【我的预约】"]
        for r in items:
            sp_name = r.space.name if r.space else f"区域ID:{r.space_id}"
            if r.seat_id:
                seat_info = f" 座位:{r.seat.seat_no}" if r.seat else f" 座位ID:{r.seat_id}"
                hc = 1
            else:
                seat_info = ""
                hc = r.headcount or 1
            lines.append(
                f"  [预约ID:{r.id}] {r.date} {r.start_time}~{r.end_time} | "
                f"{sp_name}{seat_info} | 占用:{hc}人 | {_status_text(r.status)}"
                + (f" | 备注:{r.remark}" if r.remark else "")
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
    headcount: int = 1,
    seat_id: int | None = None,
    remark: str | None = None,
) -> str:
    """创建预约。参数齐全（space_id/date/start_time/end_time）时直接调用，
    不要再问用户"确认吗"。date 格式 YYYY-MM-DD，start_time/end_time 格式 HH:mm。
    headcount 默认为1（空间级预约时用户可填写多人；座位级固定1）。
    调用前请先用 check_seat_availability 确认该时段可约。"""
    db = _db()
    try:
        sp = db.query(Space).filter(Space.id == space_id).first()
        if not sp:
            return f"区域 ID:{space_id} 不存在"
        if sp.status != 1:
            return f"区域「{sp.name}」已关闭"

        start_min = _time_to_min(start_time)
        end_min = _time_to_min(end_time)
        open_min = _time_to_min(sp.open_time or "08:00")
        close_min = _time_to_min(sp.close_time or "22:00")

        if start_min < open_min or end_min > close_min:
            return f"创建失败: 超出开放时间范围 {sp.open_time}~{sp.close_time}"
        if start_min >= end_min:
            return "创建失败: 结束时间必须晚于开始时间"

        if seat_id:
            seat = db.query(Seat).filter(Seat.id == seat_id).first()
            if not seat:
                return f"座位 ID:{seat_id} 不存在"
            if seat.status != 1:
                return f"座位「{seat.seat_no}」已停用"
            if seat.space_id != space_id:
                return f"座位「{seat.seat_no}」不属于区域「{sp.name}」"
            headcount = 1
            seat_conflicts = (
                db.query(Reservation)
                .filter(
                    Reservation.space_id == space_id,
                    Reservation.seat_id == seat_id,
                    Reservation.date == date,
                    Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.APPROVED]),
                )
                .all()
            )
            for r in seat_conflicts:
                if start_time < r.end_time and end_time > r.start_time:
                    return f"创建失败: 座位 {seat.seat_no} 在 {start_time}~{end_time} 已被预约(ID:{r.id})"
        else:
            if headcount < 1:
                return "创建失败: 占用名额至少为1"
            if headcount > sp.capacity:
                return f"创建失败: 占用名额({headcount}) 超过区域容量({sp.capacity})"

        # 容量检查
        segments, _, _, _ = _compute_capacity_segments(db, space_id, date)
        for t0, t1, occ, avail, _ in segments:
            if t0 < end_min and t1 > start_min and occ + headcount > sp.capacity:
                return (
                    f"创建失败: {date} {start_time}~{end_time} 容量不足。"
                    f"时段 {_min_to_time(t0)}~{_min_to_time(t1)} 已占 {occ}/{sp.capacity}，"
                    f"再加 {headcount} 人将超额"
                )

        reservation = Reservation(
            user_id=user_id,
            space_id=space_id,
            seat_id=seat_id,
            headcount=headcount,
            date=date,
            start_time=start_time,
            end_time=end_time,
            remark=remark,
            status=ReservationStatus.PENDING,
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)

        if seat_id:
            seat_str = f"座位:{reservation.seat.seat_no}" if reservation.seat else f"座位ID:{seat_id}"
        else:
            seat_str = f"区域级·{headcount}人"

        return (
            f"✅ 预约创建成功!\n"
            f"预约ID: {reservation.id}\n"
            f"区域: {sp.name}(ID:{space_id})\n"
            f"类型: {seat_str}\n"
            f"时间: {date} {start_time}~{end_time}\n"
            f"状态: 待审核"
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
            seat_info = ""
            if r.seat_id:
                seat_info = f" 座位:{r.seat.seat_no}" if r.seat else f" 座位ID:{r.seat_id}"
            else:
                seat_info = f" 区域级×{r.headcount or 1}人"
            return (
                f"✅ 已取消预约 ID:{reservation_id}\n"
                f"{sp_name}{seat_info} | {r.date} {r.start_time}~{r.end_time}"
            )
        if r.status == ReservationStatus.CANCELLED:
            return "该预约已经是取消状态"
        if r.status == ReservationStatus.REJECTED:
            return "已拒绝的预约无法取消"
        return f"当前状态({_status_text(r.status)})无法取消"
    except Exception as e:
        db.rollback()
        return f"取消预约失败: {e}"
    finally:
        db.close()


@tool
def rag_search(question: str) -> str:
    """从系统知识库中检索相关信息。用于回答关于预约规则、使用说明等文档类问题。"""
    try:
        from app.rag.vector_store import get_vector_store
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
    """获取当前真实日期和时间。凡涉及日期（用户说"明天"、"周五"、没说日期）
    必须先调用此工具，禁止自己编造日期。返回格式: YYYY-MM-DD。"""
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
