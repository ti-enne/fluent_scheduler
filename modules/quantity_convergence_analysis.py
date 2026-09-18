import pandas as pd
from pathlib import Path
import numpy as np
import regex as re
import matplotlib.pyplot as plt

class SteadyConvergence():
    df : pd.DataFrame
    statistics_df : pd.DataFrame
    
    def __init__(self, file_path:Path) -> None:
        self.df = pd.read_csv(
            file_path, 
            skipinitialspace=True, 
            skiprows=2, 
            sep=r"\s+",
            engine="python"
            )
        self.df.columns = [re.sub(r'\(|\)|\"',"",column_name).lower() for column_name in self.df.columns]
        values_column = self.df[self.df.columns[-1]]
        self.dominant_period = self._estimate_dominant_period(values_column)
        windows = self._split_windows(values_column.to_numpy(), self.dominant_period)
        self.statistics_df = pd.DataFrame(self._window_statistics(window) for window in windows)
        for item in ["mean","std"]:
            self._rel_change_column(item)
        self.statistics_df["converged"] = self.statistics_df.apply(self._check_convergence_tolerances,axis=1, args=(1,1,1))
        pass
    
    @staticmethod
    def _estimate_dominant_period(values:np.ndarray):
        y = values - values.mean()
        if np.allclose(y,0):
            return None
        spectrum = np.fft.rfft(y)
        freqs = np.fft.rfftfreq(len(y))
        magnitude = np.abs(spectrum)
        magnitude[:5]=0.0
        # plt.plot(magnitude)
        # plt.show()
        dominant_bin = int(np.argmax(magnitude)) #return index of the frequency with the biggest magnitude
        if freqs[dominant_bin]==0:
            return None
        frequency = float(1.0/freqs[dominant_bin])
        return round(frequency)
        
    @staticmethod
    def _split_windows(
        values: np.ndarray,
        window_size: int
    ) -> list[np.ndarray]:
        n_windows = len(values) // window_size
        return [
            values[window_size*i:window_size*(i+1)]
            for i in range(n_windows)
        ]
        
    @staticmethod
    def _window_trend(window: np.ndarray) -> float:
        x = np.arange(len(window))
        slope,_=np.polyfit(x, window,1)
        return slope
        
    def _window_statistics(self, window: np.ndarray) -> dict[str,float]:
        return {
            "mean" : np.mean(window),
            "std" : np.std(window),
            "min" : np.min(window),
            "max" : np.max(window),
            "range" : np.ptp(window),
            "trend" : self._window_trend(window), #checking slope to verify if average is still climbing/descending
        }

    def _rel_change_column(self, column_name:str):
        eps = 1e-12
        denominator = self.statistics_df[column_name].abs().combine(self.statistics_df[column_name].shift(1).abs(), np.maximum).clip(lower=eps)
        self.statistics_df[f"{column_name}_change_rel"] = self.statistics_df[column_name].diff().abs()/denominator
    
    @staticmethod
    def _check_convergence_tolerances(
        current : pd.Series,
        mean_tolerance: float = 1e-3,
        std_tolerance: float = 1e-2,
        trend_tolerance: float = 1e-5
    ) -> bool:
        return(
            current["mean_change_rel"] < mean_tolerance and
            current["std_change_rel"] < std_tolerance and
            current["trend"] < trend_tolerance
        )
        