from fastapi import HTTPException, Depends

from config.settings import settings
from engine import FluentCommission

def all_commission_list() -> list[str]:
    return [item.name for item in settings.root_folder.glob("*") if item.is_dir() and settings.commission_regex.search(item.name)]

def get_commission_or_404(commission_name:str) -> FluentCommission:
    if commission_name not in all_commission_list():
        raise HTTPException(status_code=404, detail=f"Commission {commission_name} is not valid.")
    return FluentCommission(commission_name, settings.root_folder)

def get_case_or_404(case_name, commission:FluentCommission=Depends(get_commission_or_404)):
    if case_name not in commission.