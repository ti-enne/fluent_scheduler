from pathlib import Path
import json
import regex as re
from dataclasses import dataclass, field, asdict
import shutil
from modules.commission_class import FluentCommission, FluentCase, FluentSubcase
import logging
import textwrap

logger = logging.getLogger("commission_parameters")

class CommissionParameters(FluentCommission):
    def __init__(self, name:str, root_path:Path):
        super().__init__(name, root_path)
        self.missing_files = []
        self.case_parameters_dict, self.json_path = self._build_cases_par_list_from_json()
        if len(self.case_parameters_dict)==0:
            logger.info(f"No cases to be run for commission {self.name}")
            return
        self.cases_to_simulate_list = self._build_cases_to_simulate_list()
    
    def _build_cases_par_list_from_json(self, json_name:str = "commission_parameters.json") -> tuple[dict[str,"CaseParameters"],Path]:
        json_path = self.folder_path / json_name
        with open(json_path) as f:
            commission_parameters : dict = json.load(f)
        default_case_dict = commission_parameters.pop("default_case", None)
        case_parameters_dict = {}
        for case_name, case_dict in commission_parameters.items():
            if case_name not in self.cases_dict.keys():
                logger.info(f"The case {case_name} is not present inside {self.folder_path.absolute()}. Removing it from the case parameters")
                continue
            case_parameters_dict[case_name] = CaseParameters.from_dict(parent_commission=self, case_name=case_name, input_case_dict=case_dict, default_case_dict=default_case_dict)
        return case_parameters_dict, json_path
    
    def _build_cases_to_simulate_list(self) -> list["CaseParameters"]:
        return [case for case in self.case_parameters_dict.values() if case.skip_case == False]
    
    def __str__(self) -> str:
        msg = ""
        if len(self.cases_to_simulate_list)>0:
            msg = f"Commission {self.name}:\n{"\n".join(["\t"+str(case).replace("\n", "\n\t") for case in self.cases_to_simulate_list])}"
        return msg
    
#valori standard per i case
@dataclass
class CaseParameters(FluentCase):
    parent_commission : CommissionParameters = None
    skip_case : bool = True
    data_file_quantities_list : list[str] = field(default_factory=list)
    equations_syntax_dict : dict[str,str] = field(default_factory=dict)
    subcases_parameters : dict[str,"SubcaseParameters"] = field(default_factory=dict)
    subcases_to_simulate : list["SubcaseParameters"] = field(default_factory=list)
    subcases_to_initialize : list["SubcaseParameters"] = field(default_factory=list)
    subcases_to_simulate_only : list["SubcaseParameters"] = field(default_factory=list)
    subcases_to_postprocess : list["SubcaseParameters"] = field(default_factory=list)
    subcases_to_skip : list["SubcaseParameters"] = field(default_factory=list)
    
    def __post_init__(self):
        return
    
    def __str__(self) -> str:
        msg = f"Case {self.name}:\n"
        if self.subcases_to_initialize:
            msg = msg + f"\tINITIALIZING: {" ,".join([subcase.name for subcase in self.subcases_to_initialize])}\n"
        if self.subcases_to_simulate_only:
            msg = msg + f"\tSIMULATING ONLY: {" ,".join([subcase.name for subcase in self.subcases_to_simulate_only])}\n"
        return msg    #Skippo il case nel caso non siano presenti subcase da simulare. E' una funzione da chiamare dopo perchè sennò il costruttore mi da errore.
    
    @classmethod
    def from_dict(cls, parent_commission:CommissionParameters, case_name:str, input_case_dict: dict, default_case_dict: dict) -> "CaseParameters":
        sub_par_dict_name =  "subcases_parameters"
        def_subcase_name = "default_subcase"
        subcases_parameters : dict = input_case_dict.pop(sub_par_dict_name)
        default_subcase_parameters : dict = default_case_dict[sub_par_dict_name]
        default_subcase_dict_1 = default_subcase_parameters[def_subcase_name]
        default_subcase_dict_2 = subcases_parameters.pop(def_subcase_name, None)
        input_case_dict = default_case_dict | input_case_dict
        default_subcase_dict = default_subcase_dict_1 | default_subcase_dict_2
        fluent_case = parent_commission.cases_dict[case_name]
        fluent_case_dict = fluent_case.__dict__ | {"parent_commission" : parent_commission}
        returned_case = cls(**fluent_case_dict, **input_case_dict) #generate a CaseParameters from a FluentCase avoiding the __post_init___
        subcases_parameters_dict = {}
        for subcase_name, subcase_dict in subcases_parameters.items():
            subcases_parameters_dict[subcase_name] = SubcaseParameters.from_dict(parent_case=returned_case, subcase_name=subcase_name, input_dict=subcase_dict, default_dict=default_subcase_dict)
        returned_case.subcases_parameters = subcases_parameters_dict
        returned_case.update_skip_case()
        returned_case.update_missing_files()
        return returned_case
    
    def update_skip_case(self):
        if all([subcase.skip_subcase for subcase in self.subcases_parameters.values()]) and self.skip_case==False: 
            self.skip_case = True
            logger.info(f"No subcase to be run for {self.parent_commission} -> {self.name}. Setting skip_case to True")
        self.subcases_to_simulate = [subcase for subcase in self.subcases_parameters.values() if subcase.skip_subcase==False]
        self.subcases_to_initialize = [subcase for subcase in self.subcases_parameters.values() if subcase.initialize==True]
        self.subcases_to_simulate_only = [subcase for subcase in self.subcases_to_simulate if subcase not in self.subcases_to_initialize]
        self.subcases_to_skip = [subcase for subcase in self.subcases_parameters.values() if subcase.skip_subcase==True]
    
    def update_missing_files(self):
        if not self.cas_file_path.exists():
            self.parent_commission.missing_files.append(self.cas_file_path)
    
@dataclass
class SubcaseParameters(FluentSubcase):
    parent_case : CaseParameters
    dat_path : Path = None
    parent_commission : CommissionParameters = None
    skip_subcase : bool = None
    initialize : bool = None
    time_step_size : float = None 
    save_img_every : int = None
    view_list : list[str] = field(default_factory=list)
    first_order_solve : bool = None
    first_order_iterations : int = None
    second_order_solve : bool = None
    second_order_iterations: int = None
    post_process : bool = None
    export_to_cfd_post : bool = None
    equations_dict : dict = field(default_factory=dict) #placeholder per quando creo le equazioni sostituendo i parametri
    
    def __post_init__(self):
        super().__post_init__()
        self.update_skip_subcase()
        self.update_missing_files()
    
    def update_skip_subcase(self):
        if self.first_order_solve==False or (self.first_order_solve==True and self.first_order_iterations==0):
            if self.second_order_solve==False or (self.second_order_solve==True and self.second_order_iterations==0):
                if self.export_to_cfd_post == False:
                    self.skip_subcase = True
                    print(f"No operations to do for {self._commissioncasesubcase_name}. Setting skip_subcase to True")
    
    def update_missing_files(self):
        if self.initialize:
            return
        if not self.dat_path.exists():
            self.parent_commission.missing_files.append(self.dat_path.absolute())
            
    def __eq__(self, other):
        if not isinstance(other, SubcaseParameters):
            return NotImplemented
        return self.name == other.name
    
    @classmethod
    def from_dict(cls, parent_case:CaseParameters, subcase_name:str, input_dict: dict, default_dict: dict = None) -> "SubcaseParameters":
        if default_dict is not None:
            input_dict = default_dict | input_dict
        equations_dict = parent_case.equations_syntax_dict
        variables_list = input_dict.pop("variables_list")
        default_name = f"{parent_case.name}_{subcase_name}"
        input_dict["dat_path"] = parent_case.folder_path / eval(f"f'{input_dict["dat_path"]}'")
        returned_class = cls(parent_case=parent_case, name=subcase_name, **input_dict)
        returned_class.equations_dict = returned_class.update_subcase_equations(equations_dict, variables_list)
        return returned_class
    
    @staticmethod
    def update_subcase_equations(equations_syntax_dict:dict[str,str], variables_list:list[float]) -> dict[str,str]:
        # Conto quante variabili sono presenti nelle equazioni
        var_list = []
        if len(equations_syntax_dict)>0:
            for equation_name, equation in equations_syntax_dict.items():
                var_list = var_list + re.findall(r"var\d+", equation)
        else:
            return
        max_var_value = max([int(re.search(r"\d+", item).group()) for item in var_list])
                
        #creo le equazioni personalizzate da mettere nelle named expression di Fluent
        if len(var_list)>0 and (len(variables_list)!=len(var_list) or max_var_value!=len(variables_list)): #controllo che il numero di variabili sia sufficiente.
            raise ValueError(textwrap.dedent(f'''
                            The number of parameters_list do not correspond to the variables needed.
                            equations_syntax_dict unique variables: {len(var_list)}
                            parameters_list variables: {len(variables_list)}
                            '''))
        variables_dict = {f"var{i+1}":value for i,value in enumerate(variables_list)} #preparo i dict delle variabili che poi sotituirà alla stringa
        # Faccio la sostituzione dei placeholder con il valore delle variabili
        equations_dict = {}
        for equation_name, equation in equations_syntax_dict.items():
            equations_dict[equation_name] = equation.format(**variables_dict)
        return equations_dict

if __name__ == "__main__":
    commission_name = "SVILSIM_capsula_nespresso"
    x = CommissionParameters(name=commission_name)
    pass