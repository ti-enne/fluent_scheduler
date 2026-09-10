from threading import RLock
from dataclasses import field, dataclass
from enum import Enum
import threading

from engine import CommissionParameters
from config.settings import SETTINGS

class SchedulerStateEnum(Enum):
    IDLE = "idle"
    INVALID = "invalid"
    SELECTED = "selected"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR ="error"

@dataclass
class SchedulerState:
    selected_commission: list[str] = field(default_factory=list)
    commissions : dict[str,CommissionParameters] = field(default_factory=dict)
    state : str = SchedulerStateEnum.IDLE
    progress : float = 0.0
    
class SchedulerManager:
    state:SchedulerState
    _lock:RLock
    _simulation_thread: threading.Thread | None
    _stop_event : threading.Event
    _checked_commissions_event : threading.Event
    commission_dict : dict[str,CommissionParameters]
    
    def __init__(self) -> None:
        self.state = SchedulerState()
        self._lock = RLock()
        self._simulation_thread = None
        self._stop_event = threading.Event()
        self._checked_commissions_event = threading.Event()
        self.commission_dict = {}
        
    def list_commissions(self) -> list[dict[str,str]]:
        with self._lock:
            return [
                {
                    "id": directory.name,
                    "name": directory.name,
                    "path": str(directory.absolute()),
                }
                for directory in SETTINGS.root_folder.iterdir()
                if directory.is_dir()
                and SETTINGS.commission_regex.search(directory.name)
            ]
    
    def select_commissions(self, commission_names:list[str]) -> None:
        with self._lock:
            available = {commission["name"] for commission in self.list_commissions()}
            unknown = [name for name in commission_names if name not in available]
            if unknown: raise ValueError(f"Unknown commissions: {", ".join(unknown)}")
            
            self.state.selected_commission = list(dict.fromkeys(commission_names))
            self.state.commissions.clear()
            self.state.state = SchedulerStateEnum.SELECTED
            self.state.progress = 0.0
            self._checked_commissions_event.clear()
    
    def deselect_commissions(self, commission_names:list[str]) -> None:
        with self._lock:
            available = {name for name in self.state.selected_commission}
            if not available: raise ValueError(f"At least one commission must be selected previously")
            unknown = [name for name in commission_names if name not in available]
            if unknown: raise ValueError(f"Unknown commissions: {", ".join(unknown)}")
            
            self.state.selected_commission = [name for name in self.state.selected_commission if name not in commission_names]
            self.state.commissions.clear()
            if not self.state.selected_commission: self.state.state = SchedulerStateEnum.IDLE
            self.state.progress = 0.0
            self._checked_commissions_event.clear()
    
    def check_commissions(self) -> dict[str, list[str]]:
        with self._lock:
            if not self.state.selected_commission:
                raise ValueError("No commissions selected.")
            
            if self._checked_commissions_event.is_set():
                raise ValueError("Commissions already checked")
            
            self.commission_dict: dict[str,CommissionParameters] = {}
            missing_files: dict[str,list[str]] = {}
            
            for commission_name in self.state.selected_commission:
                commission = CommissionParameters(commission_name, SETTINGS.root_folder)
                self.commission_dict[commission_name] = commission
                
                if commission.missing_files:
                    missing_files[commission_name] = [str(path) for path in commission.missing_files]
                    
            self.state.commissions = self.commission_dict
            self.state.state = SchedulerStateEnum.INVALID if missing_files else SchedulerStateEnum.READY
            self._checked_commissions_event.set()
            
            return missing_files
    
    def start_simulation(self) -> None:
        with self._lock:
            if self.state.state != SchedulerStateEnum.READY:
                raise ValueError("Scheduler is not ready to start. Check for errors in scheduled commissions.")
            
            if self._simulation_thread is not None and self._simulation_thread.is_alive():
                raise ValueError("A simulation is already running")
            
            self._stop_event.clear()
            self.state.state = SchedulerStateEnum.RUNNING
            self.state.progress = 0.0
            
            self._simulation_thread = threading.Thread(target=self._run_simulation, name="fluent-simulation", daemon=True)
            self._simulation_thread.start()
            
    def stop_simulation(self) -> None:
        with self._lock:
            if self.state.state != SchedulerStateEnum.RUNNING:
                raise ValueError("No simulation is currently running")
        self._stop_event.set()
        
    def _run_simulation(self) -> None:
        try:
            for commission_name in self.state.selected_commission:
                if self._stop_event.is_set():
                    break
            
            commission = self.state.commissions[commission_name]
            
            for case in commission.cases_to_simulate_list:
                if self._stop_event.is_set():
                    break
                
                for subcase in case.subcases_to_simulate:
                    self._run_subcase(commission, case, subcase)
            
            with self._lock:
                if self._stop_event.is_set():
                    self.state.state = SchedulerStateEnum.STOPPED
                else:
                    self.state.state = SchedulerStateEnum.COMPLETED
        except:
            with self._lock:
                self.state.state = SchedulerStateEnum.ERROR
        
    def _run_subcase(self, commission, case, subcase):
        raise NotImplementedError
            
    def get_status(self) -> dict:
        with self._lock:
            total_subcases = sum(len(case.subcases_to_simulate) for commission in self.state.commissions.values() for case in commission.cases_to_simulate_list)
            return {
                "state" : self.state.state,
                "selected_commissions":(self.state.selected_commission.copy()),
                "progress" : self.state.progress,
                "total_subcases" : total_subcases
            }
            
    