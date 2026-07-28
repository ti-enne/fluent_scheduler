from pathlib import Path
import regex as re
import logging
import matplotlib.pyplot as plt
import pandas as pd
from functools import cached_property
import shutil
from dataclasses import dataclass
from modules.postprocessing_library import OutFileElaborated, LogFileElaborated

logger = logging.getLogger("commission_class")

def remove_file_extension(string:str) -> str:
    return string.split(".")[0]

class FluentCommission:
    def __init__(self, name : str, root_path : Path = Path(r"F:\01_FLUENT_SIM")):
        self.name = name
        self.missing_files : list[Path] = []
        self.folder_path = self._build_folder_path(root_path)
        self.cases_list = self._build_cases_list()
        self.cases_dict = {case.name : case for case in self.cases_list}
    
    def _build_folder_path(self, root_path:Path) -> Path:
        folder_path = root_path / self.name / "05_Risultati" / "Analisi"
        if not folder_path.exists():
            msg = f"The folder for the commission {self.name} do not exists in {root_path}"
            logger.error(msg)
            raise FileExistsError(msg)
        return folder_path
    
    def _build_cases_list(self) -> list["FluentCase"]:
        cases_list = [folder_path for folder_path in self.folder_path.iterdir() if not re.search(r"^_|^imm",folder_path.name, flags=re.IGNORECASE) and folder_path.is_dir()]
        final_list = []
        for case_path in cases_list:
            try:
                final_list.append(FluentCase(case_path.name, self))
            except FileExistsError:
                pass
        # cases_list = [FluentCase(case_path, self) for case_path in cases_list]
        return final_list

@dataclass
class FluentCase:
    name : str
    parent_commission : FluentCommission
    folder_path : Path = None
    runs_archive_path : Path = None
    subcases_list : list["FluentSubcase"] = None
    subcases_dict : dict[str,"FluentSubcase"] = None
    cas_file_path : Path = None
    
    def __post_init__(self):
        self.folder_path = self._build_folder_path(self.folder_path)
        self.folder_path = self.folder_path / "results"
        if not self.folder_path.exists():
            msg=f"The 'results' folder for {self.parent_commission.name} -> {self.name} does not exist. Removing it from the cases list"
            logger.error(msg)
            raise FileExistsError(msg)
        self.runs_archive_path = self._build_runs_archive_path()
        self.subcases_list = self._build_subcases_list()
        self.subcases_dict = {subcase.name : subcase for subcase in self.subcases_list}
        self.cas_file_path = self._build_cas_file_path()
    
    def _build_folder_path(self, folder_path:Path) -> Path:
        if folder_path == None:
            folder_path = self.parent_commission.folder_path / self.name
        if not folder_path.exists():
            msg = f"Folder {folder_path.absolute()} do not exists."
            logger.error(msg)
            raise FileExistsError(msg)
        return folder_path 
    
    def _build_runs_archive_path(self) -> Path:
        runs_archive_path = self.folder_path / "runs_archive"
        if not runs_archive_path.exists():
            logger.info(f"The folder runs_archive for {self.parent_commission.name} / {self.name} do not exists. The folder has been created.")
            runs_archive_path.mkdir()
        return runs_archive_path
            
    def _build_subcases_list(self) -> list["FluentSubcase"]:
        dat_files_list = [file for file in self.folder_path.iterdir() if file.is_file() and re.search(fr"{self.name}(\w+)+(?!-\d+)\.dat\.h5$", file.name)]
        subcases_list = [FluentSubcase(dat_path=file_path, parent_case=self) for file_path in dat_files_list]
        if not subcases_list:
            logger.info(f"No .dat files found for subcase {self.parent_commission.name} -> {self.name}")
        return subcases_list
    
    def _build_cas_file_path(self) -> Path:
        cas_file_path = self.folder_path / f"{self.name}.cas.h5"
        if not cas_file_path.exists():
            msg = f"The cas file {cas_file_path.absolute()} is not present"
            logger.error(msg)
            self.parent_commission.missing_files.append(cas_file_path)
            # raise FileNotFoundError
        return cas_file_path
            
@dataclass
class FluentSubcase: 
    parent_case : FluentCase
    dat_path : Path
    name : str = None
    runs_list : list["FluentRun"] = None
    latest_run : "FluentRun" = None
    _commissioncasesubcase_name : str = None
    casesubcase_name : str = None
       
    def __post_init__(self):
        self.name = self._build_name()
        self.parent_commission = self.parent_case.parent_commission
        self._commissioncasesubcase_name = self._build_commissioncasesubcase_name()
        self.casesubcase_name = self._build_casesubcase_name()
        self.runs_list, self.latest_run = self._build_run_folders()        
    
    def _build_commissioncasesubcase_name(self) -> str:
        return f"{self.parent_commission.name} -> {self.parent_case.name} -> {self.name}"

    def _build_casesubcase_name(self) -> str:
        return f"{self.parent_case.name}_{self.name}"

    def _build_run_folders(self) -> tuple[list[Path], "FluentRun"]:
        run_folder_list = [item for item in self.parent_case.runs_archive_path.iterdir() if item.is_dir() and re.search(f"{self.parent_case.name}_{self.name}_run", item.name)]
        if not run_folder_list:
            logger.info(f"No runs available to be processed for {self._commissioncasesubcase_name}")
            return [], None
        run_folder_list.sort(key=lambda x: self._extract_run_value(x))
        runs_list = [FluentRun(run_path=path, parent_subcase=self) for path in run_folder_list]
        latest_run = runs_list[-1]
        return runs_list, latest_run
        
    def _build_name(self) -> str:
        name = remove_file_extension(self.dat_path.name)
        name = name.replace(f"{self.parent_case.name}_", "")
        return name
        
    def _extract_run_value(self, path:Path) -> int:
        return int(re.search(r"run(\d+)", path.name).group(1))

    def generate_new_run(self) -> "FluentRun":
        if self.latest_run != None:
            new_run = self.latest_run.index + 1
        else:
            new_run = 1
        new_path = self.parent_case.runs_archive_path / f"{self.casesubcase_name}_run{new_run}"
        new_path.mkdir()
        
        files_to_copy = self._file_list_generator(research_path=self.parent_case.folder_path, file_extension_list=[".out", "log.txt", ".flsettings"])
        for file in files_to_copy:
            new_file_path = new_path / file.name
            shutil.copy2(file, new_file_path)
        
        new_run = FluentRun(run_path=new_path, parent_subcase=self)
        self.runs_list.append(new_run)
        new_run.generate_plot_imgs(research_path=new_path)
        return new_run

    def _file_list_generator(self, research_path:Path, file_extension_list:list[str]) -> list[Path]:
        def filter_for_most_recent_file(lista:list) -> list:
            def extract_base_name(path:Path):
                return path.name.split(".")[0].split("-")[0]
            
            def get_last_modified_time(path:Path):
                return path.stat().st_mtime
            
            if not research_path.is_dir():
                logger.error("research_path must be a directory. Check your code.")
            
            grouping_dict = {extract_base_name(item):[] for item in lista}
            for file in lista:
                grouping_dict[extract_base_name(file)].append(file)
            grouping_dict = {k:sorted(value,key=lambda x:get_last_modified_time(x)) for k,value in grouping_dict.items()}
            
            new_lista = [item[-1] for item in grouping_dict.values()]
            return new_lista
        lista : list[Path] = []
        for file_ext in file_extension_list:
            if "out" in file_ext:
                add_str = r"\w+(-rfile(_\d+)*)*"
            elif "log" in file_ext:
                add_str = "_"
            else:
                add_str = ""
            pattern = re.compile(fr"{self.casesubcase_name}{add_str}{re.escape(file_ext)}$")
            lista = lista + [item for item in research_path.iterdir() if pattern.search(item.name)]
            
        if not lista:
            logger.error(f"No {' or '.join(file_extension_list)} files to copy for {self._commissioncasesubcase_name}")
            # raise FileNotFoundError
        return filter_for_most_recent_file(lista)

class FluentRun:
    def __init__(self, run_path:Path, parent_subcase:FluentSubcase):
        self.path = run_path
        self.parent_subcase = parent_subcase
        self.parent_case = parent_subcase.parent_case
        self.parent_commission = self.parent_case.parent_commission
        self.index = self._build_run_number()
        self.name = self._build_run_name()
    
    @cached_property
    def _commissioncasesubcase_name(self):
        return self.parent_subcase._commissioncasesubcase_name
    
    @cached_property
    def _casesubcase_name(self):
        return self.parent_subcase.casesubcase_name
    
    def _build_run_name(self) -> str:
        return self.path.name
    
    def _build_run_number(self) -> int:
        return int(re.search(r"_run(\d+)", self.path.name).group(1))
    
    def _extract_out_name(self, path:Path) -> str:
        name = re.search(fr"(?<={self._casesubcase_name}_).*", path.name.split(".")[0]).group()
        name = name.replace("-rfile", "")
        return name
    
    def _check_folders_existance(self):
        if not self.path:
            logger.error(f"No run folders for {self._commissioncasesubcase_name}")
            return
    
    def out_files_plotter(self, research_path:Path=None):
        out_files_list = self.parent_subcase._file_list_generator(research_path=research_path, file_extension_list=[".out"])
        out_files_list: list[OutFileElaborated] = [OutFileElaborated(item) for item in out_files_list]
        for output_file in out_files_list:
            fig_name = f"{self._casesubcase_name}_{output_file.name}.jpeg"
            fig_path = self.path / fig_name
            fig, ax = plt.subplots()
            output_file.generate_dataframe_ax(ax=ax)
            fig.savefig(fig_path, bbox_inches='tight')
            
    def log_files_plotter(self, research_path:Path=None):
        log_file = self.parent_subcase._file_list_generator(research_path=research_path, file_extension_list=["log.txt"])
        log_file = LogFileElaborated(log_file[0])
        for df_name in log_file.dataframes_dict:
            fig,ax = plt.subplots()
            log_file.df_to_ax(df_name, ax)
            fig_name = f"{self._casesubcase_name}_{df_name.lower()}.jpeg"
            fig_path = self.path / fig_name
            fig.savefig(fig_path, bbox_inches='tight')
    
    def generate_plot_imgs(self, research_path:Path=None):
        self.out_files_plotter(research_path)
        self.log_files_plotter(research_path)


if __name__=="__main__":
    commessa = "D4P26I0022-CFD_DIFFUSORE_ARIA_IMPERMEABILIZZANTE_CELLULOSA"
    commessa = FluentCommission(commessa)
    pass