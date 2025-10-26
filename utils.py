import os
import json 

base_dir = os.path.dirname(os.path.abspath(__file__))
def load_json_data(filepath: str) -> dict:
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, 'r') as f:
        return json.load(f)

def save_json_data(filepath: str, data: dict):
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, 'w') as f:
        json.dump(data, f, indent=4)