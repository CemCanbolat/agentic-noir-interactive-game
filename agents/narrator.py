"""
Narrator Agent for Agentic Noir.
Transforms structured Director events into atmospheric noir prose.
The Narrator decides HOW to describe things - the Director decides WHAT happens.
"""
import json
import os
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)


# --- Output Schema ---
class ScriptLine(BaseModel):
    """A single line of dialogue or narration for the scene."""
    speaker: str = Field(description="NARRATOR for narration, or character name for dialogue (e.g., 'MIRIAM KLINE', 'BARTENDER')")
    style: str = Field(description="TTS style hint: 'low, gravelly', 'nervous, quick', 'cold, suspicious', etc.")
    text: str = Field(description="The actual line of dialogue or narration")


class NarratorScene(BaseModel):
    """A complete scene script with multiple lines."""
    scene: List[ScriptLine] = Field(description="List of script lines that make up the scene")


narrator_parser = JsonOutputParser(pydantic_object=NarratorScene)


# --- System Prompt ---
NARRATOR_SYSTEM_PROMPT = """
You are the 'Narrator' of a film noir detective roleplaying game set in 1947.
Your voice is gritty, atmospheric, and dripping with hard-boiled poetry.
You transform structured events into immersive scenes.

## YOUR STYLE

- **Second-person for narration**: "You push through the door..." NOT "The door opens..."
- **Short, punchy sentences** mixed with longer atmospheric ones
- **Sensory details**: smoke, rain, neon, shadows, the smell of cheap whiskey
- **Film noir vocabulary**: dame, gumshoe, copper, joint, heel, patsy

## RULES

1. **NARRATOR lines**: Always second-person ("you see", "you notice")
2. **CHARACTER lines**: In-character dialogue with personality
3. **NEVER speak for the players**: Don't invent player dialogue
4. **KEEP IT BRIEF**: 2-4 lines total. Don't ramble.
5. **Match the event type** to your tone

## EVENT TYPE TEMPLATES

**location_reveal**: Describe the atmosphere, what players see. End with tension. (ONLY for entering new locations)
**item_found**: Brief moment of discovery. Focus on the ITEM, not the whole room. 1-2 sentences.
**item_inspected**: Reveal the hidden details with significance. Focus on what they learn.
**item_taken**: Short confirmation. "You pocket the evidence..." One sentence is enough.
**npc_dialogue**: Character speaks. Show personality in delivery. Don't describe the room again.
**action_blocked**: Make the failure feel real, maybe darkly humorous. Brief.
**flavor_moment**: Quick atmospheric beat. 1-2 sentences MAX. Don't re-describe the room.

## CRITICAL: DON'T REPEAT ROOM DESCRIPTIONS

- If the player is already in a room and does something, DON'T describe the room again
- Focus ONLY on the action and its result
- Example: If player "inspects the piano", describe finding something in the piano, NOT the whole room

## EXAMPLES

Event: location_reveal (entering new room)
[NARRATOR]: "You push through the door and the smell hits you first—stale beer, cheaper perfume. The Silver Gull hasn't seen better days in a decade."

Event: item_found (searching something)
[NARRATOR]: "Your fingers find a hidden latch. With a click, a compartment opens, revealing a torn paper sleeve tucked inside."

Event: item_taken
[NARRATOR]: "You slip the evidence into your coat pocket. Another piece of the puzzle."

Event: flavor_moment (doing something casual)
[NARRATOR]: "You lean against the piano, running your fingers over the dusty keys. Miriam watches you from across the room."

## COMPOUND ACTIONS (action + dialogue)

If the Director provides BOTH a description AND dialogue, include BOTH:

Event: item_taken with dialogue (taking evidence and asking about it)
[NARRATOR]: "You slip the torn sleeve into your pocket, then hold it up where Miriam can see."
[MIRIAM KLINE] (defensive, evasive): "What's that supposed to mean? It's just some old piano wire. Everyone has those around here."

---

DIRECTOR'S EVENT:
{director_event}

{format_instructions}
"""

HUMAN_PROMPT = "Create the scene for this event."

# Build prompt and chain
prompt = ChatPromptTemplate.from_messages([
    ("system", NARRATOR_SYSTEM_PROMPT),
    ("human", HUMAN_PROMPT)
])

narrator_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8, timeout=30)
narrator_chain = prompt | narrator_llm | narrator_parser


def invoke_narrator(director_event: dict) -> dict:
    """
    Transform a Director event into a narrated scene.
    
    Args:
        director_event: The narrator_event dict from DirectorDecision
    
    Returns:
        NarratorScene with list of ScriptLines
    """
    result = narrator_chain.invoke({
        "director_event": json.dumps(director_event, indent=2),
        "format_instructions": narrator_parser.get_format_instructions()
    })
    return result


def format_scene_for_display(scene: dict) -> str:
    """Format a scene for terminal display."""
    lines = []
    for line in scene.get('scene', []):
        speaker = line.get('speaker', 'NARRATOR')
        style = line.get('style', '')
        text = line.get('text', '')
        lines.append(f"[{speaker}] ({style}): {text}")
    return "\n".join(lines)


# --- TTS Integration Point ---
def speak_scene(scene: dict) -> None:
    """
    Process scene for TTS output.
    Currently prints; future: integrate with TTS API.
    """
    print("\n--- SCENE ---")
    for line in scene.get('scene', []):
        speaker = line.get('speaker', 'NARRATOR')
        style = line.get('style', '')
        text = line.get('text', '')
        
        if speaker == "NARRATOR":
            print(f"\n[NARRATOR] ({style}):\n  {text}\n")
        else:
            print(f"  [{speaker}] ({style}): \"{text}\"")
    
    print("--- END SCENE ---\n")


# --- Standalone testing ---
if __name__ == "__main__":
    # Test events
    test_events = [
        {
            "event_type": "location_reveal",
            "description": "Players enter a dimly lit bar with a piano in the corner",
            "items_visible": ["bar counter", "dusty piano", "half-empty whiskey bottles"],
            "npcs_present": ["tired bartender"],
            "dialogue": None,
            "npc_emotion": None,
            "block_reason": None
        },
        {
            "event_type": "action_blocked",
            "description": "Player tried to take the piano",
            "items_visible": [],
            "npcs_present": [],
            "dialogue": None,
            "npc_emotion": None,
            "block_reason": "The piano weighs several hundred pounds and is bolted to the stage"
        },
        {
            "event_type": "npc_dialogue",
            "description": "Bartender responds to question about the victim",
            "items_visible": [],
            "npcs_present": ["Bartender"],
            "dialogue": "Iris? Yeah, she sang here. Beautiful voice. Shame about what happened. But I don't know nothing else, detective.",
            "npc_emotion": "nervous, evasive",
            "block_reason": None
        }
    ]
    
    for i, event in enumerate(test_events):
        print(f"\n{'='*50}")
        print(f"TEST {i+1}: {event['event_type']}")
        print('='*50)
        
        try:
            scene = invoke_narrator(event)
            speak_scene(scene)
        except Exception as e:
            print(f"Error: {e}")