from pathlib import Path
import pandas as pd
import regex as re
from matplotlib.axes import Axes
import logging
from numpy import ceil

logger = logging.getLogger("postprocessing_library")

class OutFileElaborated:
    def __init__(self, path:Path):
        self.path = path
        file_lines = self._build_file_lines()
        self.name = file_lines[0].replace('"','').replace("\n","")
        self.dataframe = self._build_dataframe(file_lines)

    def _build_file_lines(self) -> list[str]:
        with open(self.path) as f:
            file_lines = f.readlines()
        return file_lines
    
    def _build_dataframe(self, file_lines:list[str]) -> pd.DataFrame:
        column_headers = re.findall(r'"(.*?)"', file_lines[2])
        dataframe = pd.read_csv(self.path, sep=r"\s+", skipinitialspace=True, skiprows=[0,1], engine="python", quotechar="'")
        dataframe.dropna(axis=1,how="all", inplace=True)
        dataframe.columns = column_headers
        if "flow-time" in dataframe.columns: dataframe.drop(labels="flow-time", axis= 1, inplace=True)
        return dataframe
    
    @staticmethod
    def _convert_name_to_axis_label(title:str) -> str:
        if bool(re.search(r"deltap", title)):
            axis_label = "delta P [Pa]"
        elif bool(re.search(r"mass_flow", title)):
            axis_label = "Mass flow [kg/s]"
        elif bool(re.search(r"static_pressure", title)):
            axis_label = "Static pressure [Pa]"
        elif bool(re.search(r"temperature", title)):
            axis_label = "Temperature [K]"
        elif bool(re.search(r"total_pressure", title)):
            axis_label = "Total pressure [Pa]"
        elif bool(re.search(r"velocity", title)):
            axis_label = "Velocity [m/s]"
        elif bool(re.search(r"balance", title)):
            axis_label = "Percentage [%]"
        else:
            axis_label = ""
        return axis_label

    def generate_dataframe_ax(self, ax=Axes) -> Axes:
        first_column_header = self.dataframe.columns[0]
        filtered_df = self.dataframe.drop(["Iteration", "Time Step"], axis=1, errors="ignore")
        
        reference_df_lenght = int(ceil(len(self.dataframe)/4))

        tailed_df = filtered_df.tail(reference_df_lenght)
        offset_percentage = 2
        max_number = tailed_df.max().max()*(1+offset_percentage/100)
        min_number = tailed_df.min().min()*(1-offset_percentage/100)

        plot_args = {
            "title" : self.name,
            "x" : first_column_header,
            "grid" : True,
            "ylim" : (min_number, max_number),
            "xlabel" : first_column_header,
            "ylabel" : self._convert_name_to_axis_label(self.name),
            "ax" : ax
        }
        
        self.dataframe.plot(**plot_args)
        ax.locator_params(nbins=20, axis="y")
        if "balance" in self.name:
            if abs(min_number)<2:
                min_number=-2
            
            if abs(max_number)<2:
                max_number=2
                
            ax.axhline(0, color='black', linestyle = ':' )
            ax.axhline(1, color='red', linestyle = ':' )
            ax.axhline(-1, color='red', linestyle = ':' )
        else:             
            try:
                dataframe_avg = filtered_df.tail(300).mean(axis=None)
            except:
                dataframe_avg = 0

            if len(self.dataframe.columns)<=2:
                ax.axhline(dataframe_avg, color='black', linestyle = ':' )
        
        ax.legend(bbox_to_anchor = (1.04, 1))
        return ax

class LogFileElaborated:
    def __init__(self, path):
        self.path = path
        self.dataframes_dict : dict[str,pd.DataFrame] = {}
        full_file = self._build_full_file()
        file_lines = full_file.split("\n")
        self.residuals_dataframe = self._build_residuals_dataframe(full_file, file_lines)
        self.pseudo_dt_dataframe = self._build_pseudo_dt_dataframe(file_lines)
        self.radiosity_dataframe = self._build_radiosity_dataframe(full_file)
    
    def _build_full_file(self) -> str:
        with open(self.path) as f:
            full_file = f.read()
        return full_file
    
    def _build_residuals_dataframe(self, full_file:str, file_lines:list[str]) -> pd.DataFrame:
        title_list : str = max(re.findall(r"^\s+iter.*", full_file, re.MULTILINE))
        title_list = title_list.split()[:-1] #ricavo gli headers del df rimuovendo time/iter
        # pattern = re.compile(r"^\s+\d+(\s+\d+(\.\d+(e(\+|-)\d+)*)*)+", re.MULTILINE)
        # residuals_list = pattern.findall(full_file)
        residuals_list = [line.split()[:-2] for line in file_lines if bool(re.search(r"^\s+\d+", line)) and not "zone" in line] #splitto ogni riga e rimuovo le colonne associate a time e iter (ultime due)
        residuals_list = [x + [None for i in range(len(title_list)-len(x))] if len(x)<len(title_list) else x for x in residuals_list] #Aggiungo none neli elementi se la colonna non è presente per evitare errori nel dataframe
        df = pd.DataFrame(residuals_list, columns=title_list)
        df = df.apply(pd.to_numeric, errors="coerce") #trasformo i dati in numerici perchè inizialmente vengono letti come stringhe
        df.reset_index(drop=True, inplace=True)
        df = df.interpolate(method="linear", limit_direction="both") #interpolo per fillare i dati nel caso in cui non siano presenti (specialmente nel caso in cui printi le convergence conditions)
        self.dataframes_dict["Residuals"] = df
        return df

    def _build_pseudo_dt_dataframe(self, file_lines:list[str]) -> pd.DataFrame|None:
        pseudo_dt_lines = [float(re.search(r"(?<=\s*Automatic.*=\s*)\d+\.\d+e(\+|\-)\d+", line).group()) for line in file_lines if bool(re.search(r"^\s*Automatic.*=\s*",line))]
        if not pseudo_dt_lines:
            logger.info("No info about pseudo-dt available. Corresponding dataframe will not be created.")
            return None
        pseudo_dt_df = pd.DataFrame(pseudo_dt_lines, columns=["Pseudo time-step [s]"])
        self.dataframes_dict["Pseudo_dt"] = pseudo_dt_df
        
        return pseudo_dt_df
        
    def _build_radiosity_dataframe(self, full_file:str) -> pd.DataFrame|None:
        matched_text = re.findall(r"(^\s+\d+(.*\n){1,5}^Final radiosity.*$)", full_file, flags=re.MULTILINE) #estraggo tutte le linee che comprendono info sulla radiosity e relativo numero di iterazione
        if not matched_text:
            logger.info("No info about radiosity available. Corresponding dataframe will not be created.")
            return None
        iteration_number_list = []
        radiosity_iterations_list = [] 
        radiosity_residuals_list = []
        for item in matched_text:
            item = item[0]
            iteration_number_list.append(int(re.search(r"(?<=\s+)\d+",item, re.MULTILINE).group()))
            radiosity_iterations_list.append(int(re.search(r"(?<=^Radiosity.*)\d+",item, re.MULTILINE).group()))
            radiosity_residuals_list.append(float(re.search(r"(?<=Final radiosity.*)\d+(.\d+e(\+|\-)\d+)",item, re.MULTILINE).group()))
        radiosity_df = pd.DataFrame(list(zip(iteration_number_list,radiosity_iterations_list,radiosity_residuals_list)), columns=["iter", "rad_iter", "rad_residuals"])
        self.dataframes_dict["Radiosity"] = radiosity_df
        return radiosity_df
        
    def df_to_ax(self, df_name:str, ax:Axes)->Axes:
        df = self.dataframes_dict[df_name]
        plot_args = {}
        if df_name.lower() != "pseudo_dt":
            plot_args = {
                "x" : "iter"
            }
            
        df.plot(title=df_name, grid=True, xlabel = "Iterations", logy=True, ax=ax, **plot_args)
        ax.legend(bbox_to_anchor = (1.04, 1))
        return ax                
