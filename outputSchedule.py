
from pathlib import Path
import json

def jsonOutput(schedule, filename="output/schedule.json"):

    with open(Path.cwd() / filename, "w", encoding="utf-8") as file:
        json.dump(schedule, file, indent=4)
       
