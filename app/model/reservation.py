import enum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.model.seat import Seat
from app.model.space import Space
from app.model.user import User


class ReservationStatus(enum.IntEnum):
    PENDING = 0
    APPROVED = 1
    REJECTED = 2
    CANCELLED = 3


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = {"comment": "座位预约"}

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), comment="预约人", nullable=False
    )
    space_id: Mapped[int] = mapped_column(
        ForeignKey("spaces.id"), comment="所属区域", nullable=False
    )
    seat_id: Mapped[int | None] = mapped_column(
        ForeignKey("seats.id"), comment="具体座位，空表示预约整个区域", nullable=True
    )
    date: Mapped[str] = mapped_column(String(20), comment="预约日期", nullable=False)
    start_time: Mapped[str] = mapped_column(String(20), comment="开始时间", nullable=False)
    end_time: Mapped[str] = mapped_column(String(20), comment="结束时间", nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    status: Mapped[int] = mapped_column(
        default=ReservationStatus.PENDING, comment="状态：0待审核，1已通过，2已拒绝，3已取消"
    )
    audit_remark: Mapped[str | None] = mapped_column(String(255), comment="审核备注")

    user: Mapped[User] = relationship()
    space: Mapped[Space] = relationship()
    seat: Mapped[Seat] = relationship()