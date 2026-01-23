"""
Director Agent for Agentic Noir.
Handles game logic, dynamic world generation, and memory management.
The Director decides WHAT happens - the Narrator decides HOW to describe it.
"""
import json
import os
from typing import Optional, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# Import memory manager
import sys
sys.path.insert(0, base_dir)
from utils import memory_manager


# --- Output Schema ---
class GeneratedItem(BaseModel):
    id: str = Field(description="Unique identifier like 'gen_dress_001'")
    name: str = Field(description="Short descriptive name")
    description: str = Field(description="Brief visual description (what you SEE, not hidden details)")
    portable: bool = Field(description="Can this item be picked up and carried?")
    category: str = Field(description="One of: clothing, papers, small_object, furniture, fixture")


class GeneratedNPC(BaseModel):
    id: str = Field(description="Unique identifier like 'gen_bartender_001'")
    name: str = Field(description="NPC's name")
    role: str = Field(description="Their job/role in the scene")
    personality: str = Field(description="2-3 personality traits")
    knowledge: List[str] = Field(description="What they know (surface level)")


class NarratorEvent(BaseModel):
    event_type: str = Field(description="One of: location_reveal, item_found, item_inspected, npc_dialogue, action_blocked, flavor_moment")
    description: str = Field(description="Brief factual description of what happened (Narrator will embellish)")
    items_visible: List[str] = Field(description="Names of items visible in scene")
    npcs_present: List[str] = Field(description="Names of NPCs present")
    dialogue: Optional[str] = Field(description="If NPC speaking, their actual dialogue", default=None)
    npc_emotion: Optional[str] = Field(description="If NPC, their emotional state", default=None)
    block_reason: Optional[str] = Field(description="If action blocked, why", default=None)


class DirectorDecision(BaseModel):
    # Core event for Narrator
    narrator_event: NarratorEvent = Field(description="Structured event data for the Narrator")
    
    # Generated content (only on first contact with new areas)
    generated_items: List[GeneratedItem] = Field(description="New items generated for this location (empty if location already visited)", default=[])
    generated_npcs: List[GeneratedNPC] = Field(description="New NPCs generated for this location", default=[])
    
    # Interactables in current scene
    interactables: List[str] = Field(description="All interactable items and people in current scene")
    
    # State changes
    new_location: str = Field(description="Current location after this action")
    clues_discovered: List[str] = Field(description="Key clue IDs discovered (c1, c2, c3)")
    suspects_interviewed: List[str] = Field(description="Suspect names interviewed")
    items_taken: List[str] = Field(description="Item IDs the player took this turn")
    progress_update: float = Field(description="Game progress 0.0 to 1.0")


director_parser = JsonOutputParser(pydantic_object=DirectorDecision)


# --- System Prompt ---
DIRECTOR_SYSTEM_PROMPT = """
You are the 'Director' of a film noir detective roleplaying game set in 1947.
You are a creative game master who controls WHAT exists and WHAT happens.
You are NOT the narrator - you output structured data, not prose.

## YOUR CORE RESPONSIBILITIES

1. **GENERATE** new content when players enter unexplored areas
2. **RETRIEVE** from memory when players revisit known areas  
3. **VALIDATE** actions against physics (can't carry a piano)
4. **PROTECT** key clues - they MUST be findable at their anchor locations
5. **NEVER** reveal the solution - players must discover it
6. **TRACK** what has been found/taken - don't re-discover items

## LOCATION SYSTEM

You receive `locations_data` with info about each location including:
- `ambient_npcs`: NPCs that should be present (bartender, engineer, etc.)
- `atmosphere`: Description hints for first visits
- `sub_locations`: Places accessible from within a building
- `initially_accessible`: Whether players can go there without discovering it first

## NAVIGATION RULES

1. **Sub-locations**: If player is inside a building (e.g., The Silver Gull), they can freely visit its sub_locations (rehearsal room, main bar, etc.)
2. **Known locations**: Check `world_state.known_locations` - player can only travel to locations they know about
3. **Location discovery**: When an NPC mentions a location (e.g., "Miriam lives on Oak Street"), add it to known_locations
4. **Unknown locations**: If player tries to go somewhere not in known_locations and it's not a sub_location, block the action and hint they need to learn about it first
5. **Sensible locations**: If player goes somewhere logical but unlisted (e.g., "the docks"), you can generate it dynamically

## FIRST VISIT TO A LOCATION

When location NOT in `world_state.visited_locations`:
- Use event_type "location_reveal" to describe the place
- Include ambient_npcs from locations_data in the scene
- Generate 3-5 FLAVOR items appropriate for the location
- Add the location to visited_locations (set new_location field)

## RETURN VISIT TO A LOCATION

When location IS in `world_state.visited_locations`:
- Do NOT re-describe the entire place
- Use existing items from memory_context
- NPCs may have moved, items stay put (unless taken)

## CRITICAL: FINDING KEY EVIDENCE - STEP BY STEP

When player searches/inspects ANY container (piano, drawer, cabinet, photo, bench, etc.):

STEP 1: Get current location from `world_state.current_location`
STEP 2: Loop through `solution.anchor_locations` and find ANY entry where:
        - The `location` field matches current location (or is similar)
        - The `container` field matches what player is searching
STEP 3: If you find a match:
        - Look up that clue ID in `solution.key_clues`
        - Describe finding that EXACT item (use the name from key_clues)
        - Add the clue ID to `clues_discovered`
        - Add the item name to `interactables`
        - DO NOT add to items_taken (player must explicitly take)
STEP 4: If NO match, generate a FLAVOR item instead

EXAMPLE:
- Player is at "The Silver Gull - rehearsal room"
- Player says "I search the piano"
- You check anchor_locations and find one with location containing "rehearsal room" and container "piano"
- You find the matching key_clue and describe finding THAT item
- You add the clue to interactables: ["piano", "Piano Wire Sleeve"]

FLAVOR items (when NO anchor_location match):
- Old letters, receipts, photos, matchbooks, personal effects, clothes
- These add atmosphere but don't solve the case
- Must NOT contradict the solution

When something IS found, ADD IT TO INTERACTABLES so player can take it!

## NPC LOCATION TRACKING - DATA-DRIVEN

1. **Check `world_state.suspect_locations`** to see where each suspect currently is
2. **If a suspect's location matches the player's current location**, include them in the scene
3. **NPCs who are at a location STAY there** until something changes
4. **Be consistent** - don't make NPCs appear/disappear randomly
5. **The data is the source of truth** - if a suspect's location in the data matches current_location, they are there

## COMPOUND ACTIONS - HANDLING MULTIPLE PARTS

When player does TWO things in one action (e.g., "take X and ask Y about it"):
1. Process BOTH parts of the action
2. Set `event_type` to the PRIMARY action (usually take/inspect)
3. BUT also include `dialogue` if they're talking to someone
4. The Narrator will handle both parts

Example: "I take the sleeve and ask Miriam about it"
- event_type: "item_taken"
- items_taken: ["c2"]
- description: "Player takes the sleeve and confronts Miriam"
- dialogue: "What's this? Just some old piano wire. Means nothing."
- npc_emotion: "defensive, nervous"

## PHYSICS RULES

PORTABLE (can take): clothing, papers, photographs, small objects, keys, letters, matchbooks, evidence
HEAVY (can push/move slightly): chairs, small tables, crates
IMMOVABLE (cannot move): furniture, safes, pianos, fixtures, radiators

If player tries to take something immovable:
- Set `narrator_event.event_type` to "action_blocked"
- Set `narrator_event.block_reason` to explain why

## KEY CLUE PROTECTION

The solution contains `anchor_locations` mapping clue IDs to their locations and containers.
When player searches a container that matches an anchor_location:
1. Check `solution.anchor_locations` for matching location + container
2. If found, describe finding it but DO NOT auto-take
3. Add the clue ID to `clues_discovered`
4. Add the found item to `interactables` so player can TAKE it
5. Only add to `items_taken` when player EXPLICITLY takes it

## FINDING vs TAKING - IMPORTANT

FINDING an item (search, inspect, look inside):
- Describe what they see
- Add to `clues_discovered` if it's a key clue
- Add found item to `interactables` list
- DO NOT add to `items_taken` yet
- event_type: "item_found" or "item_inspected"

TAKING an item (take, grab, pick up, pocket):
- Player must explicitly say they take it
- Set event_type: "item_taken"
- Add to `items_taken`
- Remove from interactables (it's now in inventory)

This applies to ALL items, not just key clues. Players should choose what to take.

## NPC DIALOGUE RULES

**CRITICAL: SUSPECTS have specific roles - read from solution.suspects!**
- Each suspect has a `description` field that tells you their role (owner, pianist, cop, etc.)
- Do NOT confuse suspects with ambient NPCs (bartender, waiter, janitor, etc.)
- If a suspect's description says "owner", they are the OWNER, not a bartender!

For SUSPECTS (from solution.suspects):
- Use their ACTUAL role from their `description` field
- Use their personality, alibi, and connection
- The culprit should lie and deflect
- Innocent suspects may be nervous but truthful  
- Add name to `suspects_interviewed`

For GENERATED NPCs (bartender, waiter, stagehand, etc.):
- Generate actual bartenders, waiters, etc. as SEPARATE NPCs
- Give them personality-appropriate responses
- They know surface-level information only
- They cannot solve the mystery for the player
- If player asks for "the bartender", generate a BARTENDER NPC, not Claude!

## NPC CONTINUITY RULES (IMPORTANT)
1. **Stick to the current conversation partner.** If player was talking to the WAITER, do not suddenly switch to the BARTENDER unless the player addresses them or moves.
2. **Be scrupulous about identity.** Do not swap "Waitress" for "Waiter" or "Bartender" randomly.
3. **If multiple NPCs are present**, specify exactly who is speaking in the `narrator_event`.

## EVENT TYPES

- `location_reveal`: Player enters/surveys a new area (ONLY use when entering a NEW location)
- `item_found`: Player searches and finds something NEW
- `item_inspected`: Player examines an item closely (reveal hidden details)
- `item_taken`: Player picks up and takes an item (ADD TO items_taken!)
- `npc_dialogue`: NPC speaks (include actual dialogue)
- `action_blocked`: Physics prevents the action
- `flavor_moment`: Minor atmospheric interaction (use for most actions IN a location)

## INTERACTABLES RULES - IMPORTANT

1. Keep interactables **STABLE** - don't invent new objects each turn
2. List only **MAJOR** interactables: furniture, people, key items (3-5 max)
3. DON'T list: dust, shadows, air, general atmosphere
4. Example: ["piano", "Miriam Kline", "bar counter"] - NOT ["dusty keys", "worn bench", "yellowed sheet music"]
5. Once you've listed items for a location, keep using the same names

## SCENE DESCRIPTION RULES - IMPORTANT

1. **location_reveal** = ONLY when player ENTERS a new location (describe the room)
2. **flavor_moment** = When player does something IN the current location (DON'T re-describe the room)
3. If player is already in a room and inspects something, use item_found/item_inspected, NOT location_reveal
4. Keep descriptions focused on the ACTION, not the entire room

## PROGRESSION RULES

- Don't make players repeat the same action multiple times
- If they search the piano bench, they find the clue on that search
- If they try to take evidence, it goes to inventory immediately
- Progress the story forward, don't stall

---

SECRET SOLUTION (NEVER REVEAL DIRECTLY):
{solution}

PHYSICS RULES:
{physics_rules}

MEMORY CONTEXT:
{memory_context}

CURRENT WORLD STATE:
{world_state}

LOCATIONS DATA:
{locations_data}

CONVERSATION HISTORY:
{conversation_history}

{format_instructions}
"""

HUMAN_PROMPT = "Player Action: {action}"

# Build prompt and chain
prompt = ChatPromptTemplate.from_messages([
    ("system", DIRECTOR_SYSTEM_PROMPT),
    ("human", HUMAN_PROMPT)
])

# llm and director_chain are now initialized inside invoke_director to support dynamic settings


# --- Helper Functions ---
def load_json_data(filepath: str) -> dict:
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, 'r') as f:
        return json.load(f)


def get_current_location(world_state: dict) -> str:
    return world_state.get("current_location", "The Silver Gull")


def invoke_director(player_action: str, world_state: dict) -> dict:
    """
    Main entry point for the Director.
    Loads context, invokes the chain, and saves generated content.
    """
    # Load data
    solution = load_json_data('data/solution.json')
    physics_rules = load_json_data('data/world_rules.json')
    locations_data = load_json_data('data/locations.json')
    
    # Get current location
    current_location = get_current_location(world_state)
    
    # Build memory context
    memory_context = memory_manager.get_relevant_context(current_location)
    
    # Get conversation history
    conversation_history = world_state.get('conversation_history', [])[-10:]
    
    # Get current custom settings
    from utils.settings_manager import get_setting
    director_model = get_setting("director_model", "gpt-4o-mini")

    # Build prompt and chain dynamically to allow model switching
    llm = ChatOpenAI(model=director_model, temperature=0.6, timeout=45)
    director_chain = prompt | llm | director_parser

    # Invoke Director
    decision = director_chain.invoke({
        "solution": json.dumps(solution, indent=2),
        "physics_rules": json.dumps(physics_rules, indent=2),
        "memory_context": json.dumps(memory_context, indent=2),
        "world_state": json.dumps(world_state, indent=2),
        "locations_data": json.dumps(locations_data, indent=2),
        "conversation_history": json.dumps(conversation_history, indent=2),
        "action": player_action,
        "format_instructions": director_parser.get_format_instructions()
    })
    
    # Save any generated content to memory
    _save_generated_content(decision, current_location)
    
    return decision


def _save_generated_content(decision: dict, location: str) -> None:
    """Persist any newly generated content to world memory."""
    
    # Save generated items
    for item in decision.get('generated_items', []):
        item_data = {
            "id": item.get('id') or item['id'],
            "name": item.get('name'),
            "description": item.get('description'),
            "portable": item.get('portable', True),
            "category": item.get('category', 'small_object'),
            "original_location": location,
            "current_location": location,
            "inspected": False,
            "taken": False
        }
        memory_manager.save_item(item_data['id'], item_data)
    
    # Save generated NPCs
    for npc in decision.get('generated_npcs', []):
        npc_data = {
            "id": npc.get('id'),
            "name": npc.get('name'),
            "role": npc.get('role'),
            "personality": npc.get('personality'),
            "knowledge": npc.get('knowledge', []),
            "current_location": location,
            "statements": []
        }
        memory_manager.save_npc(npc_data['id'], npc_data)
    
    # Save/update location memory
    if decision.get('generated_items') or decision.get('generated_npcs'):
        location_data = {
            "items": [item.get('id') for item in decision.get('generated_items', [])],
            "npcs": [npc.get('id') for npc in decision.get('generated_npcs', [])],
            "last_visited": True  # Could add timestamp
        }
        memory_manager.save_location(location, location_data)
    
    # Handle items taken
    for item_id in decision.get('items_taken', []):
        memory_manager.transfer_item_to_inventory(item_id)

