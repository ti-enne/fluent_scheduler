from fastapi import APIRouter, HTTPException

from web.dependencies import simulation_manager
from web.schemas import CommissionSelectionIn, CommissionSelectionOut, CommissionCheckOut, SchedulerStatus

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

@router.post("/check", response_model=CommissionCheckOut)
def check_commission() -> CommissionCheckOut:
    try:
        missig_files = simulation_manager.check_commissions()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    return CommissionCheckOut(state=simulation_manager.state.state, missing_files=missig_files)

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