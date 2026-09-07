from fastapi import APIRouter, HTTPException
import json

from config.settings import settings
from web.schemas import CommissionOut,CommissionParametersOut
from modules import FluentCommission

router = APIRouter(prefix="/commissions/{commission_name}", tags=["commission"])

commission_list : dict[str,FluentCommission] = {}
selected_commissions : set = {}
@router.get("/", response_model=CommissionOut)
def commision_details(commission_name:str):
    commission_path = settings.root_folder / commission_name
    if not commission_path.exists():
        raise HTTPException(status_code=404, detail=f"Folder {commission_path} do not exists")

    if commission_name in commission_list.keys():
        commission = commission_list[commission_name]
        print(commission)
    else:
        commission = FluentCommission(commission_name, root_path=settings.root_folder)
        commission_list[commission_name] = commission
    
    commission.available_cases = list(commission.cases_dict.keys())
    return commission

@router.get("/parameters", response_model=CommissionParametersOut)
def get_parameters(commission_name:str):
    commission = commission_list.get(commission_name,commision_details(commission_name))
    print(commission.folder_path)
    json_path = commission.folder_path.joinpath(settings.simulation_parameters_default_name)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"File {json_path.absolute()} not found.")
    with json_path.open("r", encoding="utf-8") as f:
        parameters = json.load(f)
    return {
        "available_cases" : commission.available_cases,
        "parameters" : parameters
    }
    
@router.post("/select")
def select_commission(commission_name:str):
    if 
    
    
    