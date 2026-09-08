import tkinter as tk
from tkinter import ttk
from pathlib import Path
import regex as re

class FileSelectorGUI:
    def __init__(self, parent:tk.Tk, base_folder:Path=Path(r"F:\01_FLUENT_SIM"), folders_regex:str=r"(^D4P\d+\w.+|SVILSIM)(-|_)\w+"):
        self.parent = parent

        self.available_files = [directory.name for directory in base_folder.iterdir() if directory.is_dir() and re.search(folders_regex, directory.name)]
        self.selected_files = []
        
        self.window = tk.Toplevel(parent)
        self.window.title = "Commission selector"

        self._build_ui()
        self._populate_source()

        self.parent.wait_window(self.window)

    def _build_ui(self):
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill="both", expand=True)

        listbox_width = 60 
        listbox_height = 20
        # Lista sinistra
        self.source_listbox = tk.Listbox(main_frame, selectmode=tk.MULTIPLE)
        self.source_listbox.config(width=listbox_width, height=listbox_height)
        self.source_listbox.grid(row=0, column=0, rowspan=4, padx=5)

        # Lista destra
        self.target_listbox = tk.Listbox(main_frame, selectmode=tk.MULTIPLE)
        self.target_listbox.config(width=listbox_width, height=listbox_height)
        self.target_listbox.grid(row=0, column=2, rowspan=4, padx=5)

        # Bottoni
        ttk.Button(main_frame, text="→", command=self.add_item).grid(row=0, column=1)
        ttk.Button(main_frame, text="←", command=self.remove_item).grid(row=1, column=1)
        ttk.Button(main_frame, text="↑", command=self.move_up).grid(row=2, column=1)
        ttk.Button(main_frame, text="↓", command=self.move_down).grid(row=3, column=1)

                # Frame inferiore (conferma / annulla)
        bottom_frame = ttk.Frame(self.window)
        bottom_frame.pack(pady=10)

        ttk.Button(bottom_frame, text="Conferma", command=self.confirm).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Annulla", command=self.cancel).pack(side="left", padx=5)
        
    def _populate_source(self):
        for f in self.available_files:
            self.source_listbox.insert(tk.END, f)

    def _refresh_target(self):
        self.target_listbox.delete(0, tk.END)
        for f in self.selected_files:
            self.target_listbox.insert(tk.END, f)

    def add_item(self):
        selection = self.source_listbox.curselection()
        if not selection:
            return

        files = [self.available_files[i] for i in selection]

        for file in files:
            if file not in self.selected_files:
                self.selected_files.append(file)
        self._refresh_target()

    def remove_item(self):
        selection = self.target_listbox.curselection()
        if not selection:
            return

        for i in sorted(selection, reverse=True):
            del self.selected_files[i]
        self._refresh_target()

    def move_up(self):
        selection = self.target_listbox.curselection()
        if not selection:
            return

        i = selection[0]
        if i == 0:
            return

        self.selected_files[i - 1], self.selected_files[i] = (
            self.selected_files[i],
            self.selected_files[i - 1],
        )

        self._refresh_target()
        self.target_listbox.select_set(i - 1)

    def move_down(self):
        selection = self.target_listbox.curselection()
        if not selection:
            return

        i = selection[0]
        if i == len(self.selected_files) - 1:
            return

        self.selected_files[i + 1], self.selected_files[i] = (
            self.selected_files[i],
            self.selected_files[i + 1],
        )

        self._refresh_target()
        self.target_listbox.select_set(i + 1)
    
    def confirm(self):
        self.selected_commissions = self.selected_files.copy()
        self.window.destroy()

    def cancel(self):
        self.selected_commissions = None
        self.window.destroy()
          
