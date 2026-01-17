import json
import os

# Get project root (assuming this file is in utils/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_json_data(filepath: str) -> dict:
    """Load JSON data from a relative path from the project root."""
    full_path = os.path.join(BASE_DIR, filepath)
    with open(full_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json_data(filepath: str, data: dict):
    """Save dictionary as JSON to a relative path from the project root."""
    full_path = os.path.join(BASE_DIR, filepath)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
