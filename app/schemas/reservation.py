from pydantic import BaseModel


class ReservationCreateRequest(BaseModel):
    lab_id: int
    equipment_id: int | None = None
    date: str
    start_time: str
    end_time: str
    remark: str | None = None


class ReservationResponse(BaseModel):
    id: int
    user_id: int
    lab_id: int
    lab_name: str | None = None
    equipment_id: int | None = None
    equipment_name: str | None = None
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
