from fastapi import APIRouter, HTTPException
import os
from pathlib import Path
import subprocess

from backend.dependencies import simulation_manager
from backend.schemas import CommissionSelectionIn, CommissionSelectionOut, CommissionCheckOut, SchedulerStatus

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

@router.post("/list-commissions")
def list_commission():
    return simulation_manager.list_commissions()

@router.post("/select", response_model=CommissionSelectionOut)
def select_commission(selection:CommissionSelectionIn) -> CommissionSelectionOut:
    try:
        simulation_manager.select_commissions(selection.commissions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    return CommissionSelectionOut(selected_commissions=simulation_manager.state.selected_commission)

@router.post("/deselect", response_model=CommissionSelectionOut)
def deselect_commission(selection:CommissionSelectionIn) -> CommissionSelectionOut:
    try:
        simulation_manager.deselect_commissions(selection.commissions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CommissionSelectionOut(selected_commissions=simulation_manager.state.selected_commission)

@router.post("/check", response_model=CommissionCheckOut)
def check_commission() -> CommissionCheckOut:
    try:
        missing_files = simulation_manager.check_commissions()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    return CommissionCheckOut(state=simulation_manager.state.state, missing_files=missing_files)

@router.get("/status", response_model=SchedulerStatus)
def get_status() -> SchedulerStatus:
    return SchedulerStatus(**simulation_manager.get_status())

@router.post("/start-simulation")
def start_simulation():
    try:
        simulation_manager.start_simulation()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return simulation_manager.get_status()

@router.post("/stop-simulation")
def stop_simulation():
    try:
        simulation_manager.stop_simulation()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return simulation_manager.get_status()

@router.post("/open-simulation-parameters")
def open_simulation_parameters() -> dict[str,str]|CommissionCheckOut:
    if not simulation_manager.state.selected_commission:
        raise HTTPException(status_code=400, detail="No commission selected")
    if not simulation_manager._checked_commissions_event.is_set():
        missing_files = check_commission()
        return missing_files
    for commission in simulation_manager.commission_dict.values():
        os.startfile(commission.json_path)
    return {"detail" : "Opening simulation parameter file for each of the selected commissions."}

@router.get("/destroy-fluent-instances")
def destroy_fluent():
    fluent_killer_path = Path(r".\fluent_killer.bat")
    subprocess.run(fluent_killer_path)
