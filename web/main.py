from fastapi import FastAPI, HTTPException
from pathlib import Path
import regex as re

from config.settings import settings
from web.schemas import CommissionOut
from modules import FluentCommission
<<<<<<< HEAD
from web.endpoints import commission_router
=======
>>>>>>> 5611e8e (Started to develop the webapp. Added FastAPI to the project and commisions endpoints and schemas)

app = FastAPI(title="Fluent scheduler", description="Web interface for Fluent scheduler", version="0.1.0")

@app.get("/")
def root():
    return{"message" : "Fluent Scheduler web interface is running"}

<<<<<<< HEAD
@app.get("/commissions/list-commissions")
def get_commissions():
=======
@app.get("/commissions")
def get_commissions(path:str):
>>>>>>> 5611e8e (Started to develop the webapp. Added FastAPI to the project and commisions endpoints and schemas)
    commission_folder_list = [
        {
            "id" : item.name,
            "name": item.name,
            "path": item.absolute()
        }
        for item in settings.root_folder.glob("*") if item.is_dir() and settings.commission_regex.search(item.name)]
    return{"commissions" : commission_folder_list}

<<<<<<< HEAD
app.include_router(router=commission_router.router)
=======
@app.get("/commissions/{commission_name}", response_model=CommissionOut)
def commision_details(commission_name:str):
    commission_path = settings.root_folder / commission_name
    if not commission_path.exists():
        raise HTTPException(status_code=404, detail=f"Folder {commission_path} do not exists")

    commission = FluentCommission(commission_name, root_path=settings.root_folder)
    return commission
    
>>>>>>> 5611e8e (Started to develop the webapp. Added FastAPI to the project and commisions endpoints and schemas)
