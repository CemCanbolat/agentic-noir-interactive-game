from agents.director import invoke_director
from agents.narrator import invoke_narrator
from utils import memory_manager
from utils.data_handler import load_json_data, save_json_data

def run_game_turn_sync(player_action: str) -> tuple:
    """
    Runs the full Director > Narrator agent pipeline.
    This is a BLOCKING (synchronous) function.
    """
    # Load current state
    world_state = load_json_data('data/world_state.json')
    
    # Run Director
    print("Director is thinking...")
    director_decision = invoke_director(player_action, world_state)
    
    # Debug output
    print("\n--- DIRECTOR'S OUTPUT (DEBUG) ---")
    print(f"Event Type: {director_decision['narrator_event']['event_type']}")
    print(f"Interactables: {director_decision['interactables']}")
    print(f"Items Taken: {director_decision.get('items_taken', [])}")
    print(f"Clues Discovered: {director_decision.get('clues_discovered', [])}")
    if director_decision.get('generated_items'):
        print(f"Generated: {[i['name'] for i in director_decision['generated_items']]}")
    print("----------------------------------\n")
    
    # Run Narrator
    print("Narrator is writing...")
    narrator_output = invoke_narrator(director_decision['narrator_event'])
    
    # Update world state
    print("Updating world state...")
    new_location = director_decision['new_location']
    world_state['current_location'] = new_location
    world_state['progress'] = director_decision['progress_update']
    
    # Track visited locations
    visited = world_state.get('visited_locations', [])
    if new_location not in visited:
        visited.append(new_location)
        world_state['visited_locations'] = visited
    
    old_clues = world_state.get('discovered_clues', [])
    old_suspects = world_state.get('interviewed_suspects', [])
    world_state['discovered_clues'] = list(set(old_clues + director_decision.get('clues_discovered', [])))
    world_state['interviewed_suspects'] = list(set(old_suspects + director_decision.get('suspects_interviewed', [])))
    
    # Handle items taken - add to inventory
    items_taken = director_decision.get('items_taken', [])
    if items_taken:
        print(f"Adding to inventory: {items_taken}")
        for item_id in items_taken:
            # For key clues (c1, c2, c3), create proper item data
            if item_id in ['c1', 'c2', 'c3']:
                solution = load_json_data('data/solution.json')
                for clue in solution.get('key_clues', []):
                    if clue['id'] == item_id:
                        item_data = {
                            'id': item_id,
                            'name': clue['name'],
                            'description': clue['description'],
                            'portable': True,
                            'category': 'evidence',
                            'is_key_clue': True
                        }
                        memory_manager.save_item(item_id, item_data)
                        break
            # Transfer to inventory
            memory_manager.transfer_item_to_inventory(item_id)
    
    conversation_history = world_state.get('conversation_history', [])
    conversation_history.append({"role": "player", "action": player_action})
    
    for line in narrator_output.get('scene', []):
        if line.get('speaker') != 'NARRATOR':
            conversation_history.append({"role": line['speaker'], "dialogue": line['text']})
    
    world_state['conversation_history'] = conversation_history[-20:]
    save_json_data('data/world_state.json', world_state)
    print("World state updated.")
    
    return director_decision, narrator_output
