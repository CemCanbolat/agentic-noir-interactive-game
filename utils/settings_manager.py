import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(BASE_DIR, "data", "settings.json")

DEFAULT_SETTINGS = {
    "director_model": "gpt-4o-mini",
    "narrator_tts_model": "gemini-2.5-flash-preview-tts"
}

def load_settings():
    """Load settings from JSON file, creating it with defaults if missing."""
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    
    try:
        with open(SETTINGS_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}. Using defaults.")
        return DEFAULT_SETTINGS

def save_settings(new_settings):
    """Save settings to JSON file."""
    # Ensure all defaults are present
    settings_to_save = DEFAULT_SETTINGS.copy()
    
    # Load existing if available to preserve unknown keys
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                current = json.load(f)
                settings_to_save.update(current)
        except:
            pass
            
    settings_to_save.update(new_settings)
    
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings_to_save, f, indent=2)
    
    return settings_to_save

def get_setting(key, default=None):
    """Get a specific setting value."""
    settings = load_settings()
    return settings.get(key, default or DEFAULT_SETTINGS.get(key))
