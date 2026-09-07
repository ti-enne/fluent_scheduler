import json
from pathlib import Path
import regex as re
from regex import Pattern
from dataclasses import dataclass

SETTINGS_FILE = Path(__file__).parent / "settings.json"

@dataclass
class GUISettings():
    root_folder:Path
    commission_regex:Pattern
    simulation_parameters_default_name:str
    
    def __post_init__(self) -> None:
        self.root_folder = Path(settings_dict["root_folder"])
        self.commission_regex = re.compile(settings_dict["commission_regex"])

with SETTINGS_FILE.open("r", encoding="utf-8") as f:
    settings_dict = json.load(f)

settings = GUISettings(**settings_dict)