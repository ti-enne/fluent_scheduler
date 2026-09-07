from pydantic import BaseModel, ConfigDict
from pathlib import Path

class CommissionInfo(BaseModel):
    name:str

class CommissionOut(BaseModel):
    name:str
    folder_path:Path
    available_cases:list
    model_config = ConfigDict(from_attributes=True)