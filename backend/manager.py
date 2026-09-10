from threading import RLock
from dataclasses import field, dataclass
from enum import Enum
import threading

from engine import CommissionParameters, FluentSolver, SubcaseParameters
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
    state : SchedulerStateEnum = SchedulerStateEnum.IDLE
    progress : float = 0.0
    completed_subcases: list[SubcaseParameters] = field(default_factory=list)
    total_subcases: list[SubcaseParameters] = field(default_factory=list)
    
class SchedulerManager:
    state:SchedulerState
    _lock:RLock
    _simulation_thread: threading.Thread | None
    _stop_event : threading.Event
    _checked_commissions_event : threading.Event
    commission_dict : dict[str,CommissionParameters]
    cores:int
    
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
            
            self.state.selected_commission = list(dict.fromkeys(commission_names)) #genero una lista di elementi unici, mantenedo l'ordine della lista di ingresso
            self.state.commissions.clear()
            self.state.state = SchedulerStateEnum.SELECTED
            self.state.progress = 0.0
            self._checked_commissions_event.clear()
    
    def deselect_commissions(self, deselected_commission_names:list[str]) -> None:
        with self._lock:
            available = {name for name in self.state.selected_commission}
            if not available: raise ValueError(f"At least one commission must be previously selected")
            unknown = [name for name in deselected_commission_names if name not in available]
            if unknown: raise ValueError(f"Unknown commissions: {", ".join(unknown)}")
            
            commission_names = [name for name in self.state.selected_commission if name not in deselected_commission_names]
            self.state.selected_commission = list(dict.fromkeys(commission_names))
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
            
            commission_dict: dict[str,CommissionParameters] = {}
            missing_files: dict[str,list[str]] = {}
            
            for commission_name in self.state.selected_commission:
                commission = CommissionParameters(commission_name, SETTINGS.root_folder)
                commission_dict[commission_name] = commission
                
                if commission.missing_files:
                    missing_files[commission_name] = [str(path) for path in commission.missing_files]
                    
            self.state.commissions = commission_dict
            self.state.state = SchedulerStateEnum.INVALID if missing_files else SchedulerStateEnum.READY
            self._checked_commissions_event.set()
            self.state.total_subcases = [subcase for commission in commission_dict.values() for case in commission.cases_to_simulate_list for subcase in case.subcases_to_simulate]
            
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
            
            cores = 36
            self._simulation_thread = threading.Thread(target=self._run_simulation, args=[cores], name="fluent-simulation", daemon=True)
            self._simulation_thread.start()
            
    def stop_simulation(self) -> None:
        with self._lock:
            if self.state.state != SchedulerStateEnum.RUNNING:
                raise ValueError("No simulation is currently running")
        self._stop_event.set()
        
    def _run_simulation(self, cores) -> None:
        try:
            for commission_name in self.state.selected_commission:
                if self._stop_event.is_set():
                    break
            
            commission = self.state.commissions[commission_name]
            
            for case in commission.cases_to_simulate_list:
                if self._stop_event.is_set():
                    break
                
                fluent_solver = FluentSolver.start_fluent(case=case, cores=cores)
                fluent_solver.load_cas()
                for subcase in case.subcases_to_simulate:
                    self._run_subcase(subcase)
            
            with self._lock:
                if self._stop_event.is_set():
                    self.state.state = SchedulerStateEnum.STOPPED
                else:
                    self.state.state = SchedulerStateEnum.COMPLETED
        except:
            with self._lock:
                self.state.state = SchedulerStateEnum.ERROR
        
    def _run_subcase(self, solver:FluentSolver, subcase:SubcaseParameters):
        subcase_solver = solver.solve_subcase(subcase)
        self.state.completed_subcases.append(subcase)
        self.state.progress = len(self.state.completed_subcases) / len(self.state.total_subcases)
            
    def get_status(self) -> dict:
        with self._lock:
            queued_subcases = [subcase.name for subcase in self.state.total_subcases if subcase not in self.state.completed_subcases]
            return {
                "state" : self.state.state,
                "selected_commissions":(self.state.selected_commission.copy()),
                "progress" : self.state.progress,
                "total_subcases" : self.state.total_subcases
            }
            
    