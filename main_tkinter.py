import tkinter as tk
from modules.tkinter_GUI.main_window import MasterWindow

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("+10+10")
    master_window = MasterWindow(root)
    root.mainloop()