from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Integer, String
from app.database import Base
from app.model.space import Space


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = {"comment": "图书馆座位"}

    space_id: Mapped[int] = mapped_column(
        ForeignKey("spaces.id"), comment="所属区域", nullable=False
    )
    seat_no: Mapped[str] = mapped_column(String(30), comment="座位编号，如 A-012", nullable=False)
    row: Mapped[str | None] = mapped_column(String(20), comment="行号")
    col: Mapped[str | None] = mapped_column(String(20), comment="列号")
    seat_type: Mapped[str | None] = mapped_column(
        String(30), comment="座位类型：普通/自习/带电源/沙发..."
    )
    has_power: Mapped[int] = mapped_column(default=0, comment="是否有电源：0无 1有")
    has_socket: Mapped[int] = mapped_column(default=0, comment="是否有USB插座：0无 1有")
    description: Mapped[str | None] = mapped_column(String(500), comment="备注")
    img: Mapped[str | None] = mapped_column(String(200), comment="图片")
    status: Mapped[int] = mapped_column(default=1, comment="状态：0-停用，1-可用")

    space: Mapped[Space] = relationship()