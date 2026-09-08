import tkinter as tk
from tkinter import ttk
from pathlib import Path
import regex as re

class SimulationQueueGUI:
    def __init__(self, parent:tk.Tk):
        self.parent_window = parent
        self.main_window = tk.Toplevel(parent)
        
        self.main_frame = ttk.Frame(self.main_window)
        self.simulations_listbox = tk.Listbox(self.main_frame, selectmode=tk.NONE)
        
