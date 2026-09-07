from fastapi import FastAPI, HTTPException
from pathlib import Path
import regex as re

from config.settings import settings
from web.schemas import CommissionOut
from modules import FluentCommission
from web.endpoints import commission_router

app = FastAPI(title="Fluent scheduler", description="Web interface for Fluent scheduler", version="0.1.0")

@app.get("/")
def root():
    return{"message" : "Fluent Scheduler web interface is running"}

@app.get("/commissions/list-commissions")
def get_commissions():
    commission_folder_list = [
        {
            "id" : item.name,
            "name": item.name,
            "path": item.absolute()
        }
        for item in settings.root_folder.glob("*") if item.is_dir() and settings.commission_regex.search(item.name)]
    return{"commissions" : commission_folder_list}

app.include_router(router=commission_router.router)