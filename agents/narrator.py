from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI 
from typing import List
import json
import os
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

def load_json_data(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def save_json_data(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

class ScriptLine(BaseModel):
    """A single line of dialogue or narration for the scene."""
    speaker: str = Field(description="The name of the character speaking (e.g., 'NARRATOR', 'MIRIAM KLINE', or an ambient NPC like 'WAITER').")
    style: str = Field(description="A brief, gritty description of the tone for the TTS (e.g., 'low, gravelly','excited, nervous', 'sharp, suspicious', 'husky, world-weary').")
    text: str = Field(description="The line of dialogue or narration, including any pauses or sighs.")

class NarratorScene(BaseModel):
    """A complete, playable scene script with multiple lines."""
    scene: List[ScriptLine] = Field(description="A list of script lines that make up the entire scene.")

# Set up the new parser
narrator_parser = JsonOutputParser(pydantic_object=NarratorScene)


narrator_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8)

# The System Prompt defines the AI's new, expanded role
narrator_system_prompt = """
You are the 'Narrator' of a film noir detective roleplaying game. 
You are the creative voice and scene director.
Your tone is gritty, hard-boiled, and atmospheric.

RULES:
1.  **CRITICAL NARRATOR RULE:** All lines for the 'NARRATOR' speaker **MUST** be written in the second-person (using "you").
    -   **GOOD:** "You push through the heavy door..."
    -   **BAD:** "The heavy door is pushed open..."
2.  **NEVER SPEAK FOR THE PLAYERS:** You **MUST NOT** invent dialogue for the players (e.g., 'DETECTIVE ONE', 'PLAYER'). This is the user's role.
3.  **Invent Ambient NPCs:** You **MAY** invent dialogue for *minor*, ambient NPCs (like a 'WAITER', 'STAGEHAND') to make the scene feel alive.
4.  **BE CONCISE:** Keep the scene short. Use 1-2 NARRATOR lines and 1-2 NPC lines at most. Do not be repetitive.
5.  **Assign Styles:** EVERY line MUST have a specific 'style' instruction for the TTS.
6.  **Output JSON:** You must output a JSON list of script lines as defined by the format instructions.

{format_instructions}
"""

# The Human Prompt will be the Director's command
narrator_human_prompt = "Director Command: {director_command}"

# Create the full prompt template
narrator_prompt_template = ChatPromptTemplate.from_messages([
    ("system", narrator_system_prompt),
    ("human", narrator_human_prompt)
])

# --- Build the Narrator Chain ---
narrator_chain = narrator_prompt_template | narrator_llm | narrator_parser

# --- Build the NEW Actor Tool ---
def speak_scene(scene: List[dict]):
    """
    This is the 'Actor Tool'. It takes the final scene list
    and processes each line for TTS.
    """
    print("\n--- SCENE START ---")
    
    for line in scene:
        speaker = line['speaker']
        style = line['style']
        text = line['text']
        
        # This print simulates the TTS call
        print(f"[{speaker}] ({style}): {text}")
        
        # In the future, this is where you'd call the Gemini TTS API
        # with the specific style and text for each line
        # tts_client.synthesize(text=text, style=style, ...)
        # and play the audio
    
    print("--- SCENE END ---\n")

def run_game_turn(player_action):
    # 1. Load current state
    world_state = load_json_data('data/world_state.json')
    solution = load_json_data('data/solution.json')

    # 2. --- DIRECTOR AGENT ---
    from director import director_chain, director_parser
    print("Director is thinking...")
    try:
        director_decision = director_chain.invoke({
            "solution": json.dumps(solution),
            "world_state": json.dumps(world_state),
            "action": player_action,
            "format_instructions": director_parser.get_format_instructions()
        })

        # 3. --- NARRATOR AGENT ---
        print("Narrator is writing...")
        narrator_output = narrator_chain.invoke({
            "director_command": director_decision['narrator_prompt'],
            "format_instructions": narrator_parser.get_format_instructions()
        })
        
        # 4. --- ACTOR TOOL ---
        # We pass the list of 'scene' dictionaries to the tool
        speak_scene(scene=narrator_output['scene'])

        # 5. --- UPDATE STATE ---
        if director_decision['interactable_list']:
            print("Interactable:", ", ".join(director_decision['interactable_list']))
        
        # (Your state saving logic here...)
        # world_state['current_location'] = director_decision['new_location']
        # ... etc ...
        # save_json_data('data/world_state.json', world_state)
        # print("World state updated.")

    except Exception as e:
        print(f"An error occurred in the game loop: {e}")

if __name__ == "__main__":
    while True:
        player_action = input("Describe your action: ")
        run_game_turn(player_action)