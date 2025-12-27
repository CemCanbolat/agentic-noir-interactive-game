import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI 
import os
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)


# --- Define Data Structures (as above) ---
class DirectorDecision(BaseModel):
    narrator_prompt: str = Field(description="A direct, gritty command for the Narrator, written in the **third-person**. It must **NEVER** use 'you'. (e.g., 'Tell detectives they find nothing.' or 'Describe the detectives finding a small paper sleeve in the piano bench.')")
    interactable_list: list[str] = Field(description="An **explicit list** of 'id' strings for all interactable items AND people in the current scene.")
    clues_discovered: list[str] = Field(description="A list of 'id' strings for any clues discovered in this turn.")
    suspects_interviewed: list[str] = Field(description="A list of 'name' strings for any suspects interviewed this turn.")
    new_location: str = Field(description="The new location of the players, if they moved. Otherwise, same as current_location.")
    progress_update: float = Field(description="A new value for the game progress, from 0.0 to 1.0.")

director_parser = JsonOutputParser(pydantic_object=DirectorDecision)

# --- Define Helper Functions ---
def load_json_data(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def save_json_data(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

# --- Define Prompt ---
system_prompt = """
You are the 'Director' of a film noir detective roleplaying game. 
You are an objective, strict, and intelligent game master. You are NOT the narrator.
You must base your response *only* on the provided SECRET SOLUTION, CURRENT STATE, and CONVERSATION HISTORY.

**CRITICAL RULES FOR ALL TURNS:**
1.  **NEVER HINT AT CLUES:** During a GENERAL action, you MUST NOT hint at a clue or its hidden location. Describing a "hidden compartment" or "loose floorboard" is a 100% failure. You must only describe the main, visible interactable item (e.g., "a piano," "a wardrobe").
2.  **CONSISTENCY IS KEY:** The `narrator_prompt` description and `interactable_list` MUST match. If you describe a 'piano' and 'Miriam Kline', the list MUST contain `['piano', 'Miriam Kline']`.
3.  **LOGICAL NPCS:** Only place NPCs in a scene if it makes narrative sense (e.g., Miriam at the piano). You can also add less significant NPCs (e.g., employees, town folk).
4.  **LANGUAGE:** Your 'narrator_prompt' is a third-person, direct command to the Narrator (NEVER use 'you').
5.  **TONE:** The tone must be gritty and to-the-point.

**GAMEPLAY LOGIC RULES:**

1.  **If the action is GENERAL** (e.g., "search the room"):
    -   Your 'narrator_prompt' must command the Narrator to briefly describe the scene (including any logical NPCs).
    -   You MUST populate the **'interactable_list'** with all key interactable items AND people (e.g., `['dressing table', 'piano', 'Miriam Kline']`).
    -   Set 'clues_discovered' to [].

2.  **If the action is SPECIFIC** (e.g., "search piano," "talk to Miriam"):
    -   **CRITICAL: YOU MUST RESOLVE THIS ACTION. DO NOT RE-DESCRIBE THE SCENE.**
    
    -   **A) If TALKING to an NPC (e.g., "ask Miriam...", "how well did you know..."):**
        -   **CRITICAL: YOU MUST PROVIDE THE SUBSTANCE OF THE REPLY.**
        -   **Check the `solution.json`:** Look at the NPC's `alibi`, `connection`, and `motive`.
        -   **Check the `conversation_history`:** See what has already been said. Do not repeat information. If the player is insisting, make the NPC's response reflect that.
        -   Your 'narrator_prompt' **MUST** command the Narrator to deliver this *specific, in-character information*.
        -   **DO NOT** be lazy. Do not just say "Tell them Miriam answers."
        -   
        -   **Player Action:** "How well did you know the victim?"
        -   **Director's Thought:** "Miriam is the culprit. Her 'connection' is 'once her closest confidante'. She will lie."
        -   **GOOD PROMPT:** "Tell them Miriam gets tense and lies, saying 'Iris? We... we were just colleagues. I barely knew her.'"
        -   
        -   **Player Action:** "That was a beautiful song, Bill Evans was it?"
        -   **Director's Thought:** "This is a 'flavor' question. Miriam is 'angular' and 'has a temper'. She's being interrogated. She will be dismissive."
        -   **GOOD PROMPT:** "Miriam ignores the compliment. Tell them she looks up from the keys and says, 'What do you want, detective?'"
        -
        -   Add the NPC's name to `interviewed_suspects`.
        -   `interactable_list` should contain the NPC being spoken to (e.g., `['Miriam Kline']`).

    -   **B) If SEARCHING a location/item (Primary Intent):**
        -   **CRITICAL: FIND ONLY. DO NOT INSPECT. THIS IS THE MOST IMPORTANT RULE.**
        -   Your 'narrator_prompt' must *only* describe finding the *physical item*.
        -   **FAILURE (DO NOT DO THIS):** "Tell them they find a sleeve *with a fingerprint*."
        -   **FAILURE (DO NOT DO THIS):** "Tell them they find a sleeve *with rosin*."
        -   **CORRECT (DO THIS):** "Tell them they find a torn paper sleeve inside the piano bench."
        -   `interactable_list` MUST contain the *name of the new clue item* (e.g., `['torn paper sleeve']`).
        -   Add the clue's 'id' to `clues_discovered`.
    
    -   **C) If INSPECTING a clue** (e.g., "inspect the paper sleeve"):
        -   This is the ONLY time you provide the full details.
        -   'narrator_prompt' describes the *deeper discovery* (e.g., "Tell them on closer inspection, the sleeve has a partial fingerprint...").
        -   `interactable_list` is `[]`.

    -   **D) If the action is a MINOR/FLAVOR interaction** (e.g., "lean on piano"):
        -   'narrator_prompt' should be a *short, descriptive beat* (e.g., "Tell them Miriam watches them warily...").
        -   `interactable_list` MUST be `[]`.
        -   DO NOT re-describe the whole room.

SECRET SOLUTION:
{solution}

CURRENT STATE:
{world_state}

CONVERSATION HISTORY (Last 10 lines):
{conversation_history}

{format_instructions}
"""

human_prompt = "Player Action: {action}"
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", human_prompt)
])

llm = ChatOpenAI( model="gpt-4o-mini", temperature=0.5, timeout=30 )
director_chain = prompt | llm | director_parser

# --- Main Game Loop ---
def run_game_turn(player_action):
    # 1. Load current state
    world_state = load_json_data('data/world_state.json')
    solution = load_json_data('data/solution.json')

    # 2. Invoke the Director chain
    print("Director is thinking...")
    try:
        decision = director_chain.invoke({
            "solution": json.dumps(solution),
            "world_state": json.dumps(world_state),
            "action": player_action,
            "format_instructions": director_parser.get_format_instructions()
        })
                
        # 3. THIS IS WHERE YOU CALL THE NARRATOR
        # For now, we'll just print its instructions
        print("\n--- To Narrator ---")
        print(decision['narrator_prompt'])
        if decision['interactable_list']:
            print("Interactable:", ", ".join(decision['interactable_list']))

        print("-------------------\n")

        # 4. Update and save the new world state
        world_state['current_location'] = decision['new_location']
        world_state['progress'] = decision['progress_update']
        # Add new, unique clues
        world_state['discovered_clues'] = list(set(world_state['discovered_clues'] + decision['clues_discovered']))
        world_state['interviewed_suspects'] = list(set(world_state.get('interviewed_suspects', []) + decision.get('interviewed_suspects', [])))
        
        save_json_data('data/world_state.json', world_state)
        print("World state updated.")

    except Exception as e:
        print(f"An error occurred: {e}")
        print("Retrying might be necessary or check your prompt/parser.")

# --- Example of running the game ---
if __name__ == "__main__":
    # Make sure your 'data' folder and JSON files exist
    
    # # First Turn
    # print("--- TURN 1 ---")
    # player_action_1 = "We've just arrived at the backstage dressing room. We want to search the room for clues."
    # print(player_action_1)
    # run_game_turn(player_action_1)

    # # Second Turn (example)
    # print("\n--- TURN 2 ---")
    # player_action_2 = "We'll check the rehearsal room. We search the piano."
    # print(player_action_2)

    # run_game_turn(player_action_2)

    while True:
        player_action = input("Describe your action: ")
        run_game_turn(player_action)
        