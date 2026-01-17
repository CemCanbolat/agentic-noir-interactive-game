import json
import os
from utils import memory_manager
from utils.data_handler import BASE_DIR, save_json_data

class GameState:
    """Global game state manager."""
    def __init__(self):
        self.in_lobby = True
        self.current_case = "iris_bell"
    
    def start_game(self, case_id: str = "iris_bell"):
        self.in_lobby = False
        self.current_case = case_id
        reset_game()
    
    def reset_to_lobby(self):
        self.in_lobby = True

# Global instance
game_state = GameState()

def reset_game():
    """Reset both world state and world memory for a new game."""
    template_path = os.path.join(BASE_DIR, "data", "default_world_state.json")
    world_state_path = os.path.join(BASE_DIR, "data", "world_state.json")
    try:
        with open(template_path, "r", encoding='utf-8') as f:
            template_data = json.load(f)
        with open(world_state_path, "w", encoding='utf-8') as f:
            json.dump(template_data, f, indent=4)
        print("World state reset to template.")
    except Exception as e:
        print(f"Failed to reset world state: {e}")
    
    memory_manager.reset_memory()
    print("World memory reset.")
