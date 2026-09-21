import regex as re
from pathlib import Path
from ansys.fluent.core.session_solver import Solver
import ansys.fluent.core as pyfluent
import pandas as pd

from .commission_parameters import SubcaseParameters
from .commission_class import FluentRun
from .fluent_flags import FluentTimeDiscretization

class TranscriptElaborator:
    column_values : list[dict[str,float]]
    _column_names : list[str]
    _pending_line : dict[str,float]
    fluent_run: FluentRun
    df: pd.DataFrame
    
    def __init__(self, fluent_run:FluentRun) -> None:
        self._pending_line = {}
        self.column_values = []
        self._column_names = []
        self.fluent_run = fluent_run
        self.df = pd.DataFrame()
    
    def elaborate_msg(self, msg:str):
        msg = msg.strip()
        self._get_column_titles(msg)
        self._get_transient_flow_info(msg)
        self._get_pseudo_dt_info(msg)
        self._get_film_values(msg)
        self._get_column_values(msg)
        
    @staticmethod
    def _extract_number(string:str, lookbehind_regex:str=None)->float:
        regex_str = r"\d+(\.\d+)*([eE][+-]\d+)*"
        if isinstance(lookbehind_regex, str):
            regex_str = fr"(?<={lookbehind_regex})"+regex_str
        value = float(re.search(regex_str,string).group())
        return value

    def add_to_pending(self, item:dict[str,float]):
        if "film_time" not in item.keys() and bool(self._pending_line.keys() & item.keys()):
            self.column_values.append(self._pending_line)
            self._pending_line = {}

        self._pending_line.update(item)

    def _get_column_titles(self, msg:str)->list[str]:
        if not msg.startswith("iter"):
            return
        self._column_names = msg.split()
        if self._column_names[-1] == "time/iter":
            splitted = self._column_names.pop(-1).split("/")
            splitted[-1] = "missing_iteration"
            self._column_names = self._column_names + splitted
    
    def _get_column_values(self, msg:str):
        if not bool(re.search(r"^\d+.*\d+$", msg)):
            return
        column_values = msg.split()
        if len(self._column_names) > len(column_values):
            results_dict = dict(zip(self._column_names[:-2], column_values[:-2]))
            results_dict.update(dict(zip(self._column_names[-2:], column_values[-2:])))
        else:
            results_dict = dict(zip(self._column_names, column_values))
        self.add_to_pending(results_dict)
    
    def _get_pseudo_dt_info(self, msg:str):
        regex = "Automatic flow pseudo-dt = "
        if not msg.startswith(regex):
            return
        self.add_to_pending({"pseudo-dt" : self._extract_number(msg, regex)})
        
    def _get_transient_flow_info(self, msg:str) -> None | float:
        if not msg.startswith("Flow time"):
            return
        results_dict={
            "flow_time" : self._extract_number(msg, "Flow time = "),
            "time_step" : self._extract_number(msg, "time step = ")
        }
        self.add_to_pending(results_dict)
        return results_dict["flow_time"]
    
    def _get_film_values(self, msg:str) -> None | float:
        if not msg.startswith("Film time"):
            return
        results_dict = {
            "film_time" : self._extract_number(msg, "Film time = "),
            "film_timestep" : self._extract_number(msg, "timestep = "),
            "film_max_cfl" : self._extract_number(msg, "max_cfl: ")
        }
        self.add_to_pending(results_dict)
        return results_dict["film_time"]
    
    def update_df(self) -> pd.DataFrame:
        # self.column_values.append(self._pending_line)
        self.df = pd.DataFrame(self.column_values+[self._pending_line])
    
    def export_to_csv(self):
        self.update_df()
        save_path = self.fluent_run.path / f"{self.fluent_run.parent_subcase.casesubcase_name}_transcript_df.csv"
        self.df.to_csv(save_path, index=False)
        
    def compose_df(self) -> tuple[pd.DataFrame, list[int]]:
        qty_name, fluent_run = next(iter(self.fluent_run.out_files_dict.items()), None)
        df = fluent_run.dataframe
        if df.empty:
            return
        
        first_iter = df.iloc[0,0]
        if first_iter <= 1 or self.fluent_run.index==1:
            return self.df
        
        runs_list = self.fluent_run.parent_subcase.get_runs_list()
        composed_df = self.df
        from_runs = [self.fluent_run.index]
        for run in reversed(runs_list):
            if run.index >= self.fluent_run.index:
                continue
            
            prev_df = run.out_files_dict[qty_name].dataframe
            last_iter = prev_df.iloc[-1,0]
            if first_iter not in [last_iter, last_iter+1]:
                continue
            
            first_iter = prev_df.iloc[0,0]
            composed_df = pd.concat([TranscriptElaborator.from_fluent_run(run).df, composed_df])
            from_runs.append(run.index)
            if first_iter <=1:
                break
            
        return composed_df, from_runs
    
    @classmethod
    def from_fluent_run(cls, fluent_run:FluentRun) -> "TranscriptElaborator":
        with open(fluent_run.log_file.path) as f:
            lines = f.readlines()
        if not re.search(r"Transcript Start Time",lines[0]):
            print("WARNING: The file given doesn't seems to be a Fluent transcript file.")
        transcript = cls(fluent_run)
        for line in lines:
            transcript.elaborate_msg(line)
        transcript.update_df()
        return transcript
    
class TranscriptElaboratorRuntime(TranscriptElaborator):
    solver : Solver
    time_discretization : FluentTimeDiscretization
    callback_list : list[str]
    subcase_params : SubcaseParameters
    max_transient_time : float
    max_film_time : float
    
    def __init__(self, solver:Solver, fluent_run:FluentRun, time_discretization:FluentTimeDiscretization, subcase_params:SubcaseParameters, max_transient_time:float=None, max_film_time:float=None) -> None:
        super().__init__(fluent_run=fluent_run)
        self.solver = solver
        self.time_discretization = time_discretization
        self.max_transient_time = max_transient_time
        self.max_film_time = max_film_time
        self.subcase_params = subcase_params
        
    def print_to_fluent_console(self, msg:str):
        self.solver.scheme.eval(f'(display "!!!FROM PYTHON SCRIPT: {msg}\n")')

    def _setup_save_img(self) -> tuple[Path,list[str]]:
        graphics = self.solver.settings.results.graphics
        contour_list = [item for item in graphics.contour().keys() if "-animation" in item]
        if not contour_list:
            print("No countours to save animations from")
            return
        if not self.subcase_params.view_list:
            print("No views to save animations from")
            return
        
        self.solver.tui.display.set.rendering_options.driver("null")
        base_path = self.fluent_run.path / "animations"
        if not base_path.exists(): base_path.mkdir()
        graphics.picture = {
                "invert_background" : True,
                "landscape" : True,
                "color_mode" : "color",
                "use_window_resolution" : False,
                "standard_resolution" : '2K QHD (2560x1440)'
            }
        return base_path, contour_list

    def _define_save_image_cb_steady(self, base_save_path:Path, contour_list:list[str]) -> str:
        if self.time_discretization != FluentTimeDiscretization.STEADY:
            return
        
        # film_time = [x for x in self.solver.rp_vars("wall-film/solution-state") if "elapsed_time" in x[0]][0][1]
        graphics = self.solver.settings.results.graphics
        def on_iteration_end(session, event_info:pyfluent.IterationEndedEventInfo):
            if event_info.index % self.subcase_params.save_img_every !=0:
                return
            for contour_name in contour_list:
                self.print_to_fluent_console(f'Saving images for contour {contour_name}, iteration: {event_info.index}')
                graphics.contour[contour_name].display()
                for view_name in self.subcase_params.view_list:
                    save_path = base_save_path / f"{self.subcase_params.casesubcase_name}_{contour_name}_{view_name}_iter{event_info.index}"
                    graphics.views.restore_view(view_name=view_name)
                    graphics.views.auto_scale()
                    graphics.picture.save_picture(file_name=save_path.absolute())

        cbid = self.solver.events.register_callback(pyfluent.SolverEvent.ITERATION_ENDED, on_iteration_end)
        return cbid
            
    def _define_save_image_cb_transient(self, base_save_path:Path, contour_list:list[str]) -> str:
        if self.time_discretization == FluentTimeDiscretization.STEADY:
            return
        
        graphics = self.solver.settings.results.graphics
        self.total_time = self.solver.rp_vars("flow-time")
        self._next_image_time = self.total_time + (self.subcase_params.save_img_every - self.total_time % self.subcase_params.save_img_every)
        def on_timestep_end(session, event_info:pyfluent.TimestepEndedEventInfo):
            self.total_time = self.solver.rp_vars("flow-time")
            if self.total_time<self._next_image_time:
                # self.print_to_fluent_console(f'Flow time is {self.total_time} and next save time is {self._next_image_time}, skipping')
                return
            
            for contour_name in contour_list:
                self.print_to_fluent_console(f'Saving images for contour {contour_name}, time: {self.total_time}')
                graphics.contour[contour_name].display()
                for view_name in self.subcase_params.view_list:
                    total_time_str = f"{self.total_time:.2e}".replace(".","d")
                    contour_name_edited = contour_name.replace("-animation","") #some names could be too long to be saved.
                    save_path = base_save_path / f"{self.subcase_params.casesubcase_name}_{contour_name_edited}_{view_name}_time{total_time_str}s"
                    graphics.views.restore_view(view_name=view_name)
                    graphics.views.auto_scale()
                    graphics.picture.save_picture(file_name=save_path.absolute())
            self._next_image_time += self.subcase_params.save_img_every

        cbid = self.solver.events.register_callback(pyfluent.SolverEvent.TIMESTEP_ENDED, on_timestep_end)
        return cbid    
    
    def define_image_callbacks(self):
        if self.subcase_params.save_img_every in [0,None]: return
        img_args = self._setup_save_img()
        if img_args is None: return
        self._define_save_image_cb_steady(*img_args)
        self._define_save_image_cb_transient(*img_args)
        
    def _stop_simulation(self, actual_time:float, max_time:float):
        if max_time == None:
            return
        if actual_time < max_time:
            return
        
        self.print_to_fluent_console("Max time reached, stopping the simulation")
        i=0
        while(i<5):
            if self.solver != None:
                try:
                    self.solver.execute_tui("(cx-interrupt)")
                except Exception:
                    print("Calculation stopped")
            i = i + 1

    def _get_transient_flow_info(self, msg: str):
        actual_time = super()._get_transient_flow_info(msg)
        if actual_time == None:
            return
        if self.max_transient_time != None and actual_time >= self.max_transient_time:
            self._stop_simulation(actual_time, self.max_transient_time)
    
    def _get_film_values(self, msg: str):
        actual_film_time = super()._get_film_values(msg)
        if actual_film_time == None:
            return
        if self.max_film_time != None and actual_film_time >= self.max_film_time:
            self._stop_simulation(actual_film_time, max_time=self.max_film_time)