from pydantic import BaseModel


class ReservationCreateRequest(BaseModel):
    space_id: int
    seat_id: int | None = None
    date: str
    start_time: str
    end_time: str
    remark: str | None = None


class ReservationResponse(BaseModel):
    id: int
    user_id: int
    space_id: int
    space_name: str | None = None
    seat_id: int | None = None
    seat_no: str | None = None
    date: str
    start_time: str
    end_time: str
    remark: str | None = None
    status: int
    audit_remark: str | None = None
    user_name: str | None = None

    class Config:
        from_attributes = True


class ReservationAuditRequest(BaseModel):
    status: int
    audit_remark: str | None = None