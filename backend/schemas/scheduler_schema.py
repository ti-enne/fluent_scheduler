from pydantic import BaseModel, Field

class CommissionSelectionIn(BaseModel):
    commissions: list[str] = Field(default_factory=list)

class CommissionSelectionOut(BaseModel):
    selected_commissions : list[str]
    
class CommissionCheckOut(BaseModel):
    state: str
    missing_files: dict[str, list[str]]

class SchedulerStatus(BaseModel):
    state: str
    selected_commissions: list[str]
    progress: float
    total_subcases: int