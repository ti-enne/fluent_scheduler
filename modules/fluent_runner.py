from dataclasses import dataclass, field
import regex as re
from pathlib import Path
import ansys.fluent.core as pyfluent
from ansys.fluent.core.streaming_services.events_streaming import SolverEvent
from ansys.fluent.core.session_solver import Solver
import subprocess
import send2trash as s2t
import datetime
from modules.commission_parameters import CommissionParameters, CaseParameters, SubcaseParameters
import logging
import textwrap
from modules.fluent_flags import FluentSolverFlags,FluentSpatialSchemes
from threading import Event
from numpy import ceil

logger = logging.getLogger(__name__)
fluent_killer_path: Path =  Path(r"F:\01_FLUENT_SIM\UTILITIES_FLUENT\fluent_killer.bat")

@dataclass
class FluentSolver:
    def __init__(self, solver_instance : Solver, case: CaseParameters, cores:int=4):
        self.solver = solver_instance
        self.case = case
        self.cores = cores
    
    @classmethod
    def start_fluent(cls, case:CaseParameters, cores:int, gpu:bool=False, use_cluster:bool=False, cwd:Path=Path("."), host_ip:str=None, host_file:Path=None) -> "FluentSolver":
        if use_cluster and any([i==None for i in [host_file, host_ip]]):
            msg = "You must specify host_ip and host_file if using cluster"
            logger.error(msg)
            raise ValueError(msg)
        
        fluent_args = {
            "processor_count" : cores,
            "gpu" : gpu,
            "ui_mode" : "gui",
            "cwd" : r"F:\01_FLUENT_SIM\fluent_logs"
        }

        # Starting the fluent session
        max_retry_attempts = 10
        retry_attempt = 0
        while retry_attempt < max_retry_attempts:
            logger.info("Starting Fluent...")
            try:
                if use_cluster:
                    #Il nodo master è il ws-e063-0024 al quale è associato l'ip 192.168.50.1. Il ws-e063-0100 ha l'ip 192.168.50.2
                    add_arg = fr"-host_ip={host_ip} -t{cores} -cnf={host_file.absolute()} -mpi=intel"
                    fluent_session = pyfluent.launch_fluent(additional_arguments=add_arg, **fluent_args)
                else:
                    fluent_session = pyfluent.launch_fluent(**fluent_args)
                break
            except Exception as e:
                msg = textwrap.dedent(f'''
                                    Fluent session not started, trying again... Retry number {retry_attempt}: Error\t{e}
                                    Error type:\t{type(e)}
                                    Error:\t{repr(e)}
                                    ''')
                logging.error(msg)
                print(msg)
                subprocess.run(fluent_killer_path) #Kill ALL the Fluent processes
                retry_attempt = retry_attempt + 1
                if retry_attempt == max_retry_attempts:
                    msg = "Solver could not be started. Stopping the script."
                    logger.error(msg)
                    raise (msg)
        
        return cls(solver_instance=fluent_session, cores = cores, case=case)
    
    def quit_fluent(self):
        self.solver.exit()
        
    def load_cas(self) -> FluentSolverFlags:
        logger.info("="*80, extra={"plain":True})
        logger.info(f"Loading case {self.case.parent_commission.name} -> {self.case.name}")
        self.solver.settings.file.read(file_type="case", file_name=self.case.cas_file_path)
        self.solver.tui.solve.set.expert("n", "n", "n")
        self.solver.settings.file.batch_options.confirm_overwrite = False #Enable auto-confirm on solver prompt
        self.residuals = self.solver.settings.solution.monitor.residual
        self.solver.chdir(str(self.case.folder_path.absolute()))

    def solve_subcase(self, subcase:SubcaseParameters):
        subcase_solver = FluentSubcaseSolver(fluent_solver=self, subcase=subcase)
        subcase_solver.solve_subcase()
        logger.info("-"*80, extra={"plain":True})
        return subcase_solver
    
    def solve_all_subcases(self):
        self.solver_time_discretization = self.load_cas()
        for subcase in self.case.subcases_to_simulate:
            self.solve_subcase(subcase=subcase)
        self.quit_fluent()

class FluentSubcaseSolver:
    def __init__(self, fluent_solver:FluentSolver, subcase:SubcaseParameters) -> None:
        self.fluent_solver = fluent_solver
        self.solver = fluent_solver.solver
        self.subcase = subcase
        self.case = self.subcase.parent_case
        self.commission = self.subcase.parent_commission
        self.to_be_solved = True if any([self.subcase.first_order_solve, self.subcase.second_order_iterations]) else False
    
    def solve_subcase(self):
        self.residuals = self.solver.settings.solution.monitor.residual
        logger.info(f"Setting up {self.subcase._commissioncasesubcase_name}.")
        self.time_discretization = self._build_time_discretization()
        self.spatial_discretization = self._build_spatial_discretization()
        self._manage_named_expressions()
        self._manage_report_files()
        self._initialize_subcase()
        self.start_time = datetime.datetime.now() #Modifico lo start time della simulazione
        self.date_formatting = "%d/%m/%Y %H:%M"
        self._subcase_calculation()
        self._export_to_cfd_post()

    def _manage_convergence_conditions(self, active:bool=True)->None:
        logger.debug(f"Setting convergence conditions to active={active}")
        convergence_conditions = self.solver.settings.solution.monitor.convergence_conditions.convergence_reports
        if len(convergence_conditions())==0:
            return
        for convergence_condition in convergence_conditions():
            convergence_conditions[convergence_condition] = {
                "active" : active,
                "print" : active
            }

    def _build_time_discretization(self):
        fluent_solver_mode = self.solver.settings.setup.general.solver.time() #Time discretization type
        return FluentSolverFlags(fluent_solver_mode)
    
    def _build_spatial_discretization(self) -> FluentSpatialSchemes:
        if self.subcase.first_order_solve:
            spatial_discretization = FluentSpatialSchemes.FIRST_ORDER_UW
        else:
            spatial_discretization = FluentSpatialSchemes.SECOND_ORDER_UW
        return spatial_discretization

    def _initialize_subcase(self):
        #Inizializzo o carico il file .dat del subcase
        if self.subcase.initialize:
            self.solver.settings.solution.initialization.initialization_type = "standard"
            self.solver.settings.solution.initialization.initialize() #Doppia inizializzazione perchè in caso di UDF nel materiale devo prima inizializzare per computare i defaults.
            self.solver.tui.solve.initialize.compute_defaults.all_zones()
            self.solver.settings.solution.initialization.initialize()
        else:
            self.solver.settings.file.read(file_type="data", file_name=self.subcase.dat_path.absolute())

    def _subcase_calculation(self):
        if not self.to_be_solved:
            msg = f"No simulations to do for subcase {self.subcase.name}"
            logger.info(msg)
            return
        self._manage_named_expressions()
        self._manage_report_files()
        self._manage_solution_verbosity()
        time_step_size = self._manage_time_step()
        self._manage_auto_save()
        self._manage_UDS_equations()
        self._start_transcript()
        cbid = self._define_save_img_callback()
        cbid = self._define_transcript_callback(max_film_time=5)
        self._manage_residuals()
        self.solver.settings.file.write(file_type="case", file_name=self.case.cas_file_path) #To avoid auto-save writing .cas file.
        self._solve_first_order()
        self._solve_second_order()
        self._solve_UDS_equations()
        self.solver.settings.parallel.timer.usage()
        self.solver.settings.file.stop_transcript()
        self.solver.tui.file.write_settings(f"{self.subcase.casesubcase_name}.flsettings")
        self.end_time = datetime.datetime.now()       
        self.simulation_time = self.end_time - self.start_time
        self.solver.settings.file.write(file_type="case", file_name=self.case.cas_file_path)
        logger.info(f"End of simulation:\nStarted at: {self.start_time.strftime(self.date_formatting)}\nFinished at: {self.end_time.strftime(self.date_formatting)}\nSimulation duration: {self.simulation_time}")
        self._post_simulation_subcase()

    def _manage_named_expressions(self):
        equations_dict = self.subcase.equations_dict
        if equations_dict==None or len(equations_dict)==0:
            return
        for equation_name, equation_definition in equations_dict.items():
            self.solver.settings.setup.named_expressions[equation_name] = {"definition" : equation_definition}
    
    def _manage_report_files(self):
        if self.subcase.post_process == False:
            return
        #Gestione dei report files
        report_files = self.solver.settings.solution.monitor.report_files
        for rp_file in report_files().keys():
            report_file_path = self.case.folder_path / f"{self.subcase.casesubcase_name}_{rp_file}-rfile.out"
            try:
                s2t.send2trash(report_file_path)
            except:
                pass
            report_files[rp_file]={
                "file_name" : report_file_path,
                "active" : True
            }
    
    def _manage_solution_verbosity(self):
        #attivo il verbosity se sto utilizzando lo pseudo_time self.solver
        try:
            self.solver.settings.solution.run_calculation.pseudo_time_settings.verbosity = 1
        except:
            print("Verbosity not active. No info on time-step will be provided")
            
        # self.solver.settings.solution.calculation_activity.solution_animations.clear() #rimuovo tutte le animazioni da Fluent. Danno bug quando modifico il path in cui salvarle tramite script (Il method esiste anche se non viene autocompletato)
    
    def _manage_time_step(self):
        #Perchè se leggo il .dat mi viene modificato il time-step in automatico.
        if  self.time_discretization == FluentSolverFlags.STEADY:
            return
        try:
            time_step_size = self.solver.settings.solution.run_calculation.transient_controls.time_step_size()
        except:
            time_step_size = None
            logger.info("No time-step size to read. Skipping.")
        
        return time_step_size
        
    def _manage_auto_save(self):
        auto_save_dict = {
            'root_name': f'./{self.subcase.casesubcase_name}',
            "case_frequency" : "if-mesh-is-modified",
            "retain_most_recent_files" : True,
        }
        if self.time_discretization == FluentSolverFlags.STEADY:
            every_n_iter = ceil(max([self.subcase.first_order_iterations, self.subcase.second_order_iterations])/3)
            if every_n_iter < 100:
                every_n_iter = 100
            #attivo l'autosave visto che Fluent ha la tendenza di crashare.
            steady_autosave_dict = {
                "data_frequency" : every_n_iter, #ogni quante iter/Time step salvare
                'max_files': 1 # numero max di file recenti
            }
            auto_save_dict = auto_save_dict | steady_autosave_dict
        
        self.solver.settings.file.auto_save = auto_save_dict
    
    def _manage_UDS_equations(self, active:bool=False):
        #Gestisco le equazioni delle UDS in modo che vengano risolte a posteriori.
        equations = self.solver.settings.solution.controls.equations
        if not hasattr(self, "_uds_equations"):
            self._uds_equations = [item for item in equations().keys() if re.search(r"uds", item)]
            if len(self._uds_equations)==0:
                logger.info("No UDS to solve or manage")
        if not self._uds_equations:
            return []
        for eq in equations:
            if eq in self._uds_equations:
                equations[eq] = active
            else:
                equations[eq] = not active
    
    def _start_transcript(self):
        # Gestisco il file transcript prodotto
        transcript_file_path = self.case.folder_path / f"{self.subcase.casesubcase_name}_log.txt"
        try:
            if transcript_file_path.exists(): 
                transcript_file_path.unlink() #Elimino il file nel caso esista, sennò errore.
        except:
            logger.info(f"{transcript_file_path.name} do not exists.")
        self.solver.settings.file.start_transcript(file_name=transcript_file_path.absolute()) #Inizio a scrivere il file di transcript.

    def _define_save_img_callback(self) -> str:
        every_n_iteration = self.subcase.save_img_every
        if every_n_iteration in [0,None]:
            return
        graphics = self.solver.settings.results.graphics
        base_path = self.case.folder_path / "animations"
        contour_list = [item for item in graphics.contour().keys() if "-animation" in item]
        if not contour_list:
            return
        if not base_path.exists(): base_path.mkdir()
        graphics.picture = {
                "invert_background" : True,
                "landscape" : True,
                "color_mode" : "color",
                "use_window_resolution" : False,
                "standard_resolution" : '2K QHD (2560x1440)'
            }
        
        def on_iteration_end(session, event_info:pyfluent.IterationEndedEventInfo):
            if event_info.index % every_n_iteration !=0:
                return
            for contour_name in contour_list:
                graphics.contour[contour_name].display()
                for view_name in self.subcase.view_list:
                    graphics.views.restore_view(view_name=view_name)
                    graphics.views.auto_scale()
                    save_path = base_path / f"{contour_name}_{view_name}_iter{event_info.index}"
                    graphics.picture.save_picture(file_name=save_path.absolute())

        cbid = self.solver.events.register_callback(pyfluent.SolverEvent.ITERATION_ENDED, on_iteration_end)
        return cbid
        
    def _define_transcript_callback(self, max_film_time=None) -> str:
        self.transcript_list = []
        calculation_ended_event = Event()
        walls_BC = self.solver.settings.setup.boundary_conditions.wall
        wall_BC_list = list(walls_BC().keys())
        wall_film_model_active = False
        if "wall_film" in walls_BC()[wall_BC_list[0]]:
            # self.solver.tui.define.models.eulerian_wallfilm.initialize_wallfilm_model()
            wall_film_model_active = True

        def on_calculation_end(session, event_info:pyfluent.CalculationsEndedEventInfo):
            calculation_ended_event.set()
        
        def stop_simulation():
            i=0
            while(i<10 and not calculation_ended_event.is_set()):
                print(on_calculation_end)
                self.solver.execute_tui("(cx-interrupt)")
                i = i + 1
        
        max_film_time = max_film_time
        def on_transcript_message(msg:str):
            msg=msg.strip()
            self.transcript_list.append(msg)
            get_film_info(msg=msg, max_film_time=max_film_time)
        
        def get_film_info(msg:str, max_film_time:float=None)->dict[str,float]:
            if not msg.startswith("Film time") or not wall_film_model_active:
                return
            results_dict = {}
            results_dict["film_time"] = extract_number(msg, "Film time = ")
            results_dict["timestep"] = extract_number(msg, "timestep = ")
            results_dict["max_cfl"] = extract_number(msg, "max_cfl: ")
            self.transcript_list.append(results_dict)
            if results_dict["film_time"] >= max_film_time and isinstance(max_film_time, (float,int)):
                logger.info("Max fill time reached, stopping the simulation")
                stop_simulation()
            return
        
        def extract_number(string:str, lookbehind_regex:str=None)->float:
            regex_str = r"\d+\.\d+([eE][+-]\d+)*"
            if isinstance(lookbehind_regex, str):
                regex_str = fr"(?<={lookbehind_regex})"+regex_str
            value = float(re.search(regex_str,string).group())
            return value
                
        cbid = self.solver.transcript.register_callback(on_transcript_message)
        self.solver.transcript.start(write_to_stdout=True)
        return cbid
            
    def _manage_residuals(self):
        residuals = self.solver.settings.solution.monitor.residual
        residuals.options.residual_values.compute_local_scale = True
        
        if self.time_discretization != FluentSolverFlags.STEADY: #transient
            residuals.options.criterion_type = "relative or absolute" # Only exists if the study is transient
            #Equation name [abs residuals, rel residuals]
            residuals_criteria={
                "continuity": [1e-4,1e-2], 
                ".*-velocity": [1e-5,1e-3], 
                "k": [1e-5,1e-3],
                "omega": [1e-5,1e-3],
                "epsilon": [1e-5,1e-3],
                "energy": [1e-7,1e-5],
                "vf-.*": [1e-3,1e-2] #multiphase residual
            }
        else: #steady-state
            if self.spatial_discretization == FluentSpatialSchemes.FIRST_ORDER_UW:
                residuals_criteria={
                    "continuity": [1e-4,1e-3], 
                    ".*-velocity": [1e-5,1e-4], 
                    "k": [1e-5,1e-4],
                    "omega": [1e-5,1e-4],
                    "epsilon": [1e-5,1e-4],
                    "energy": [1e-7,1e-6],
                    "vf-.*": [1e-3,1e-2] 
                }
            else:
                residuals_criteria={
                    "continuity": [1e-4,1e-2], 
                    ".*-velocity": [1e-5,1e-3], 
                    "k": [1e-5,1e-3],
                    "omega": [1e-5,1e-3],
                    "epsilon": [1e-5,1e-3],
                    "energy": [1e-7,1e-5],
                    "vf-.*": [1e-3,1e-2] 
                }
            
        for item in residuals.equations():
            for key,value in residuals_criteria.items():
                if re.match(key, item):
                    residuals.equations[item] = {
                        "absolute_criteria" : value[0],
                        "relative_criteria" : value[1],
                    }

    def _solve_first_order(self):
        if not self.subcase.first_order_solve:
            return
        discretization_schemes = self.solver.settings.solution.methods.spatial_discretization.discretization_scheme
        self.spatial_discretization = FluentSpatialSchemes.FIRST_ORDER_UW.value
        discretization_schemes["mom"] = self.spatial_discretization
        self._manage_residuals()
        if self.time_discretization == FluentSolverFlags.STEADY:
            self.solver.settings.solution.run_calculation.iter_count = self.subcase.first_order_iterations
            logger.info(f"Solving steady-state first-order simulation.\nStarted at: {self.start_time.strftime(self.date_formatting)}")
        else:
            self.solver.settings.solution.run_calculation.transient_controls = {
                'time_step_count': self.subcase.first_order_iterations,
                'time_step_size': self.subcase.time_step_size,
            }
            logger.info(f"Solving transient first-order simulation.\nStarted at: {self.start_time.strftime(self.date_formatting)}")
        self.solver.settings.solution.run_calculation.calculate()
        logger.info(f"Finished {self.time_discretization.value} first-order simulation")
        dat_file_path = self.case.folder_path / f"{self.subcase.casesubcase_name}_1storder.dat.h5"
        self.solver.settings.file.write(file_type="data", file_name=dat_file_path.absolute()) #salvo il .dat
        
    def _solve_second_order(self):
        if not self.subcase.second_order_solve:
            return
        discretization_schemes = self.solver.settings.solution.methods.spatial_discretization.discretization_scheme
        self.spatial_discretization = FluentSpatialSchemes.SECOND_ORDER_UW.value
        discretization_schemes["mom"] = self.spatial_discretization
        self._manage_residuals()
        if self.time_discretization == FluentSolverFlags.STEADY:
            second_order_no_convcond_iter = 100
            if second_order_no_convcond_iter < self.subcase.second_order_iterations:
                logger.info(f"Solving steady-state second-order with convergence conditions disabled.\nStarted at: {self.start_time.strftime(self.date_formatting)}")
                self._manage_convergence_conditions(active=False)
                self.solver.settings.solution.run_calculation.iter_count = second_order_no_convcond_iter
                self.solver.settings.solution.run_calculation.calculate()
                self.subcase.second_order_iterations = self.subcase.second_order_iterations - second_order_no_convcond_iter
                logger.info(f"Solving steady-state second-order simulation.\nStarted at: {self.start_time.strftime(self.date_formatting)}")
                self._manage_convergence_conditions(active=True)
        else:
            self._manage_convergence_conditions(active=False)
            self.solver.settings.solution.run_calculation.transient_controls = {
                'time_step_count': self.subcase.second_order_iterations,
                'time_step_size': self.subcase.time_step_size,
            }
            logger.info(f"Solving transient second-order simulation.\nStarted at: {self.start_time.strftime(self.date_formatting)}")
        self.solver.settings.solution.run_calculation.calculate()
        logger.info(f"Finished {self.time_discretization.value} second-order simulation")
        dat_file_path = self.case.folder_path / f"{self.subcase.casesubcase_name}.dat.h5"
        self.solver.settings.file.write(file_type="data", file_name=dat_file_path.absolute()) #salvo il .dat

    def _solve_UDS_equations(self, iter:int=200):
        if len(self._uds_equations)==0:
            return []
        self._manage_UDS_equations(active=True)
        discretization_schemes = self.solver.settings.solution.methods.spatial_discretization.discretization_scheme
        uds_equation_names = [item for item in discretization_schemes() if item.startswith("uds")]
        for eq in uds_equation_names:
            discretization_schemes[eq] = FluentSpatialSchemes.SECOND_ORDER_UW.value
        logger.info("Solving UDS equations")
        if iter > self.subcase.second_order_iterations:
            iter = self.subcase.second_order_iterations
        self.solver.settings.solution.run_calculation.iter_count = iter
        self.solver.settings.solution.run_calculation.calculate()
        self._manage_UDS_equations(active=False)
        logger.info("Finished UDS simulation")
            
    def _post_simulation_subcase(self):
        logger.info("Initiating postprocessing...")
        #Creo il file che tiene traccia delle simulazioni effettuate nel caso non esista.
        analisi_folder_path = self.case.folder_path.parent
        log_file_path = analisi_folder_path / "simulation_log.txt"
        if not log_file_path.exists(): #creo il file se non esistente
            with open(log_file_path, "w") as f:
                pass
        
        all_simulations_log_file = Path(r"F:\01_FLUENT_SIM\UTILITIES_FLUENT\all_sim_log_file.txt")
        if not all_simulations_log_file.exists():
            with open(all_simulations_log_file, "w") as f:
                pass            
        
        new_run = self.subcase.generate_new_run()
        try:
            with open(log_file_path, "a") as f:
                f.write(f"{new_run.name}\t{self.end_time}\t{self.subcase.casesubcase_name}\tdurata simulazione: {self.simulation_time}\tnumero di core: {self.fluent_solver.cores}\n")
            
            with open(all_simulations_log_file, "a") as f:
                f.write(f"{self.end_time}\t{self.commission.name}\t{self.subcase.casesubcase_name}\tdurata simulazione: {self.simulation_time}\tnumero di core: {self.fluent_solver.cores}\n")
        except Exception as e:
            logger.error(f"Log file could not be written or the subcase was not simulated. Error {e}")
        logger.info("Postprocessing finished.")


    def _export_to_cfd_post(self):
        if not self.subcase.export_to_cfd_post:
            return
        qtys_list = self.case.data_file_quantities_list
        self.solver.tui.file.export.cdat_for_cfd_post__and__ensight(self.subcase.casesubcase_name, "()", "*", "()", " ".join(qtys_list), "()", "n")