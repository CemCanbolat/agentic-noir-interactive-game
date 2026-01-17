"""
Memory Manager for the Agentic Noir game.
Handles persistence and retrieval of dynamically generated world content.
"""
import json
import os
from typing import Optional, Dict, List, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_PATH = os.path.join(BASE_DIR, "data", "world_memory.json")
DEFAULT_MEMORY_PATH = os.path.join(BASE_DIR, "data", "default_world_memory.json")


def load_memory() -> dict:
    """Load the current world memory."""
    try:
        with open(MEMORY_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _get_default_memory()


def save_memory(memory: dict) -> None:
    """Save the world memory to disk."""
    with open(MEMORY_PATH, 'w') as f:
        json.dump(memory, f, indent=4)


def _get_default_memory() -> dict:
    """Return a fresh memory structure."""
    return {
        "generated_locations": {},
        "generated_items": {},
        "generated_npcs": {},
        "team_inventory": {"bag": [], "pockets": []},
        "player_notes": []
    }


def reset_memory() -> None:
    """Reset world memory to default state."""
    save_memory(_get_default_memory())


# --- Location Memory ---

def get_location_memory(location_id: str) -> Optional[dict]:
    """
    Get memory for a specific location.
    Returns None if location hasn't been visited yet.
    """
    memory = load_memory()
    return memory["generated_locations"].get(location_id)


def save_location(location_id: str, location_data: dict) -> None:
    """Save generated content for a location."""
    memory = load_memory()
    memory["generated_locations"][location_id] = location_data
    save_memory(memory)


def location_exists(location_id: str) -> bool:
    """Check if a location has been visited/generated."""
    memory = load_memory()
    return location_id in memory["generated_locations"]


# --- Item Memory ---

def get_item(item_id: str) -> Optional[dict]:
    """Get a specific item's data."""
    memory = load_memory()
    return memory["generated_items"].get(item_id)


def save_item(item_id: str, item_data: dict) -> None:
    """Save a generated item."""
    memory = load_memory()
    memory["generated_items"][item_id] = item_data
    save_memory(memory)


def update_item(item_id: str, updates: dict) -> None:
    """Update an existing item's properties."""
    memory = load_memory()
    if item_id in memory["generated_items"]:
        memory["generated_items"][item_id].update(updates)
        save_memory(memory)


def transfer_item_to_inventory(item_id: str, container: str = "bag") -> bool:
    """
    Move an item from its location to team inventory.
    Returns True if successful.
    """
    memory = load_memory()
    item = memory["generated_items"].get(item_id)
    
    if not item:
        print(f"[Memory] Item {item_id} not found in memory")
        return False
    
    # Check if item is portable
    if not item.get("portable", True):
        print(f"[Memory] Item {item_id} is not portable")
        return False
    
    # Check if already in inventory
    if container not in memory["team_inventory"]:
        memory["team_inventory"][container] = []
    
    if item_id in memory["team_inventory"][container]:
        print(f"[Memory] Item {item_id} already in inventory")
        return True  # Already there, still success
    
    # Add to inventory
    memory["team_inventory"][container].append(item_id)
    print(f"[Memory] Added {item_id} to {container}")
    
    # Update item location
    item["current_location"] = f"inventory.{container}"
    item["taken"] = True
    
    # Remove from original location if tracked there
    original_loc = item.get("original_location")
    if original_loc and original_loc in memory["generated_locations"]:
        loc_data = memory["generated_locations"][original_loc]
        if "items" in loc_data:
            loc_data["items"] = [i for i in loc_data["items"] if i.get("id") != item_id]
    
    save_memory(memory)
    return True


# --- NPC Memory ---

def get_npc(npc_id: str) -> Optional[dict]:
    """Get a specific NPC's data."""
    memory = load_memory()
    return memory["generated_npcs"].get(npc_id)


def save_npc(npc_id: str, npc_data: dict) -> None:
    """Save a generated NPC."""
    memory = load_memory()
    memory["generated_npcs"][npc_id] = npc_data
    save_memory(memory)


def add_npc_statement(npc_id: str, statement: str, turn: int) -> None:
    """Record something an NPC said (for consistency)."""
    memory = load_memory()
    if npc_id in memory["generated_npcs"]:
        if "statements" not in memory["generated_npcs"][npc_id]:
            memory["generated_npcs"][npc_id]["statements"] = []
        memory["generated_npcs"][npc_id]["statements"].append({
            "turn": turn,
            "said": statement
        })
        save_memory(memory)


# --- Inventory ---

def get_inventory() -> dict:
    """Get the current team inventory."""
    memory = load_memory()
    return memory.get("team_inventory", {"bag": [], "pockets": []})


def get_inventory_items() -> List[dict]:
    """Get full item data for all items in inventory."""
    memory = load_memory()
    inventory = memory.get("team_inventory", {})
    items = []
    
    for container, item_ids in inventory.items():
        for item_id in item_ids:
            item = memory["generated_items"].get(item_id)
            if item:
                item["container"] = container
                items.append(item)
    
    return items


# --- Context Building ---

def get_relevant_context(current_location: str) -> dict:
    """
    Build a context object with only relevant memory for the Director.
    This keeps token usage efficient.
    """
    memory = load_memory()
    
    context = {
        "current_location_memory": memory["generated_locations"].get(current_location),
        "inventory": get_inventory_items(),
        "nearby_npcs": [],
        "location_visited_before": current_location in memory["generated_locations"]
    }
    
    # Get NPCs at current location
    for npc_id, npc_data in memory["generated_npcs"].items():
        if npc_data.get("current_location") == current_location:
            context["nearby_npcs"].append(npc_data)
    
    return context


# --- Memory Pruning ---

def prune_old_locations(keep_count: int = 10) -> None:
    """
    Remove old location memories to keep memory size manageable.
    Keeps the most recently visited locations.
    """
    memory = load_memory()
    locations = memory["generated_locations"]
    
    if len(locations) <= keep_count:
        return
    
    # Sort by last_visited timestamp if available
    sorted_locs = sorted(
        locations.items(),
        key=lambda x: x[1].get("last_visited", 0),
        reverse=True
    )
    
    # Keep only the most recent
    memory["generated_locations"] = dict(sorted_locs[:keep_count])
    save_memory(memory)
