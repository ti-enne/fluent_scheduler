import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
from pathlib import Path
import subprocess
import logging
import os
from ansys.fluent.core.streaming_services.events_streaming import SolverEvent
import datetime
import time
from enum import Enum, auto

from modules.fluent_runner import FluentSolver
from modules.commission_parameters import CommissionParameters
from modules.tkinter_GUI.file_selector import FileSelectorGUI
from modules.tkinter_GUI.simulation_queue_GUI import SimulationQueueGUI 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

root_logger = logging.getLogger()
base_folder = Path(r"F:\01_FLUENT_SIM")
folders_regex = r"(^D4P\d+\w.+|SVILSIM)(-|_)\w+"

class TkinterTextHandler(logging.Handler):
    """Custom handler which writes log messages to GUI textbox."""
    
    def __init__(self, text_widget: scrolledtext.ScrolledText):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.after(0, self._write, msg)

    def _write(self, msg):
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.see(tk.END)
        
class QueueEvents(Enum):
    CALC_DONE = auto()
    JSON_MODIFIED = auto()

y_padding = 5

class MasterWindow(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.file_checking_event = threading.Event()
        self.root = root
        self.root.title("Fluent runner")
        
        self._build_top_frame()
        self._build_progress_bar()
        self.commissions_name_list = []
        self._build_buttons_frame()
        self._build_cores_frame()

        # Queue for comunication between threads and GUI
        self.queue_results = queue.Queue()
        self.queue_running = queue.Queue()
        
        self._build_log_area()
    
    def _build_top_frame(self):
        self.top_frame = tk.Frame(self.root)
        self.top_frame.pack(pady=y_padding)
        self.top_label = ttk.Label(self.top_frame, text="Choose commissions")
        self.top_label.pack(pady=y_padding, side="left", expand=True, fill="x")
    
    def _build_progress_bar(self):
        self.progress = ttk.Progressbar(self.root, mode='determinate', length=300)
        self.progress.pack(pady=y_padding)

    def _build_buttons_frame(self):
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(pady=y_padding)
        self.choose_commission_button = ttk.Button(self.button_frame, text="Choose commission", command=self.select_commission)
        self.choose_commission_button.pack(padx=10, pady=y_padding, side="left")
        self.check_files_button = ttk.Button(self.button_frame, text="Check simulation files", command=self.check_simulation_files, state="disabled")
        self.check_files_button.pack(padx=10, pady=y_padding, side="left")
        self.open_json_button = ttk.Button(self.button_frame, text="Open commissions params", command=self.open_commission_parameters_file, state="disabled")
        self.open_json_button.pack(padx=10, pady=y_padding, side="left")
        self.start_simulation_button = ttk.Button(self.button_frame, text="Start simulation", command=self.start_simulation, state="disabled")
        self.start_simulation_button.pack(padx=10, pady=y_padding, side="left")
    
    def _build_cores_frame(self):
        self.cores_frame = ttk.Frame(self.root)
        self.cores_frame.pack(pady=0.5)
        ttk.Label(self.cores_frame,text="Simulation cores:").pack(side="left")
        self.cores_entry = ttk.Entry(self.cores_frame)
        self.cores_entry.pack(pady=y_padding, side="right")
        self.cores_entry.insert(index=tk.END,string=str(36))

    def _build_log_area(self):
        self.text_area = scrolledtext.ScrolledText(self.root, wrap = tk.WORD)
        self.text_area.pack(padx=10, pady=y_padding)

    def select_commission(self):
        """
        Opens a window where you can select commissions to simulate.
        Updates the attribute commission_name_list.
        """
        dlg = FileSelectorGUI(self.root, base_folder=base_folder, folders_regex=folders_regex)
        if len(dlg.selected_commissions)>0:
            self.commissions_name_list = dlg.selected_commissions
            self.check_files_button.config(state=tk.ACTIVE)
            self.top_label.config(text="Check simulation files")
        
    def check_simulation_files(self):
        """
        Generate the commission class for the simulation and check if all the necessary files are present inside the folders.
        """
        
        self.commissions_list = [CommissionParameters(name=commission_name, root_path=base_folder) for commission_name in self.commissions_name_list]
        files_not_found_list = [str(e) for commission in self.commissions_list for e in commission.missing_files] # Doppia list comprehesion perchè *lista non funziona
        if len(files_not_found_list)>0:
            self.text_area.insert(tk.INSERT, chars=f"{"\n".join(files_not_found_list)}\n")
            self.check_files_button.config(text="Check again")
            return
        
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.INSERT, chars="\n".join([str(commission) for commission in self.commissions_list]))
        
        self.start_simulation_button.config(state=tk.ACTIVE)
        self.open_json_button.config(state=tk.ACTIVE)
        
        total_number_of_subcases = sum([1 for commission in self.commissions_list for case in commission.case_parameters_dict.values() for subcase in case.subcases_to_simulate])
        if total_number_of_subcases > 0:
            self.progress_bar_step = int(100/total_number_of_subcases)
        else:
            self.progress_bar_step = 0
        
        file_check_thread = threading.Thread(target=self.check_if_modified, daemon=True)
        file_check_thread.start()

    def check_if_modified(self):
        """
        Controls if commission parameters files are modified before starting the simulation.

        Args:
            stop_event (threading.Event): Event which stops the file checking.
        """
        last_mtimes = {}
        file_path_list = [commission.json_path for commission in self.commissions_list]
        for file_path in file_path_list:
            last_mtimes[file_path] = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
        
        while not self.file_checking_event.is_set():
            time.sleep(1)
            for file_path in file_path_list:
                file_actual_date = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
                if last_mtimes[file_path] != file_actual_date:
                    last_mtimes[file_path] = file_actual_date
                    answer = messagebox.askokcancel(master = self.root, 
                                       message="One of the commission_parameters file has been modified.\nDo you want to reload the file?",
                                       title="Commission parameters modified",
                                       icon = messagebox.QUESTION)
                    if answer == True:
                        self.check_simulation_files()
                        return
                
    def open_commission_parameters_file(self):
        """
        Opens the commission_parameters.json files of the selected commissions
        """
        for commission in self.commissions_list:
            os.startfile(commission.json_path)
        
    def start_simulation(self):
        """
        Starts the simulation of the selected commissions
        """
        self.file_checking_event.set()
        cores = int(self.cores_entry.get())
        self.text_area.delete("1.0", tk.END)
        self.check_files_button.config(state=tk.DISABLED)
        # self.open_json_button.config(state=tk.DISABLED)
        self.start_simulation_button.config(text="Stop current simulation", command=self.stop_fluent_simulation)
        self.start_simulation_button.pack_info()
        self.new_frame = ttk.Frame(self.root)
        self.new_frame.pack(before=self.cores_frame, pady=y_padding)
        self.stop_iteration_button = ttk.Button(self.new_frame, text="Stop current simulation", state=tk.DISABLED)
        self.stop_iteration_button.pack(side=tk.LEFT)
        self.destroy_fluent_button = ttk.Button(self.new_frame, text="Destroy ALL Fluent instances", command=self.destroy_fluent)
        self.destroy_fluent_button.pack(side=tk.LEFT)
        self.simulation_queue_button = ttk.Button(self.new_frame, text="Simulation queue", command=self.show_simulations_queue)
        self.simulation_queue_button.pack(side=tk.LEFT)
        self.cores_frame.destroy()
        self.start_simulation_button.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.top_label.config(text="Running...")

        self.log_area = scrolledtext.ScrolledText(self.root, wrap = tk.WORD)
        self.log_area.pack(padx=10, pady=y_padding)
        
        # Run simulation thread
        thread = threading.Thread(target=self.start_simulation_thread, args=(cores,), daemon=True)
        thread.start()
        
        # Check queue to update GUI
        self.check_queue()
    
    def start_simulation_thread(self, cores):
        i=0 #simulation counter
        for commission in self.commissions_list:
            log_handler = TkinterTextHandler(self.log_area)
            log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            root_logger.addHandler(log_handler)
        
            def calc_end(session, event_info):
                self.callback = SolverEvent.CALCULATIONS_ENDED
            for case in commission.cases_to_simulate_list:
                fluent_solver = FluentSolver.start_fluent(case=case, cores=cores)
                fluent_solver.load_cas()
                fluent_solver.solver.events.register_callback(SolverEvent.CALCULATIONS_ENDED, calc_end)
                self.after(0, lambda: self.stop_iteration_button.configure(state=tk.ACTIVE, command=lambda: self.stop_fluent_simulation(fluent_solver.solver)))
                for subcase in case.subcases_to_simulate:
                    self.callback = None
                    subcase_solver = fluent_solver.solve_subcase(subcase)
                    #contatore delle simulazioni e update del progress bar
                    i=i+1
                    self.queue_results.put([i*self.progress_bar_step, f"{subcase._commissioncasesubcase_name} finished.\nStarted at: {subcase_solver.start_time}\tEnd time: {subcase_solver.end_time}\nTotal time: {subcase_solver.simulation_time}"])
                    
                fluent_solver.quit_fluent()
        self.queue_results.put(QueueEvents.CALC_DONE)  # Segnale di completamento
        
    def check_queue(self):
        """Checks queue and updates GUI"""
        try:
            while not self.queue_results.empty():
                q_results = self.queue_results.get_nowait()
                if q_results == QueueEvents.CALC_DONE:
                    self.top_label.config(text="Simulations completed!")
                    self.check_files_button.config(state=tk.NORMAL)
                    return
                else:
                    self.progress["value"] = q_results[0]  # Aggiorna la barra di progresso
                    self.text_area.configure(state=tk.NORMAL)
                    self.text_area.insert(tk.INSERT, q_results[1]+"\n")
                    self.text_area.configure(state=tk.DISABLED)
                
            while not self.queue_running.empty():
                q_running = self.queue_running.get_nowait()
                self.top_label.config(text=q_running)

        finally:
            # Controlla di nuovo tra 100ms
            self.root.after(1000, self.check_queue)

    def destroy_fluent(self):
        fluent_killer_path = Path(r".\fluent_automation\fluent_killer.bat")
        subprocess.run(fluent_killer_path)
        # sys.exit(0)
    
    def stop_fluent_simulation(self, solver):
        self.stop_iteration_button.configure(state=tk.DISABLED)
        i=0
        while(self.callback!=SolverEvent.CALCULATIONS_ENDED or i<10):
            solver.execute_tui("(cx-interrupt)")
            i = i + 1
        self.callback = None
    
    def show_simulations_queue(self):
        SimulationQueueGUI(self.root)
    
