from fastapi import APIRouter, HTTPException
import json

from config.settings import settings
from web.endpoints import commission_router
from web.endpoints.commission_router import commission_list

router = APIRouter(prefix=commission_router.router.prefix+"/{case_name}", tags=["case"])

@router.get("/")
def case_info(commission_name:str, case_name:str):
    