from pydantic import BaseModel, ConfigDict


class SeatResponse(BaseModel):
    id: int
    space_id: int
    space_name: str | None = None
    seat_no: str
    row: str | None = None
    col: str | None = None
    seat_type: str | None = None
    has_power: int
    has_socket: int
    description: str | None = None
    img: str | None = None
    status: int

    model_config = ConfigDict(from_attributes=True)


class SeatCreateRequest(BaseModel):
    space_id: int
    seat_no: str
    row: str | None = None
    col: str | None = None
    seat_type: str | None = None
    has_power: int = 0
    has_socket: int = 0
    description: str | None = None
    img: str | None = None
    status: int = 1


class SeatUpdateRequest(BaseModel):
    space_id: int | None = None
    seat_no: str | None = None
    row: str | None = None
    col: str | None = None
    seat_type: str | None = None
    has_power: int | None = None
    has_socket: int | None = None
    description: str | None = None
    img: str | None = None
    status: int | None = None