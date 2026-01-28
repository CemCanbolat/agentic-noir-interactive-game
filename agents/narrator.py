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
from google import genai
import uuid

# Load environment
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)


# --- Output Schema ---
class ScriptLine(BaseModel):
    """A single line of dialogue or narration for the scene."""
    speaker: str = Field(description="NARRATOR for narration, or character name for dialogue (e.g., 'MIRIAM KLINE', 'BARTENDER')")
    style: str = Field(description="TTS style hint: 'low, gravelly', 'nervous, quick', 'cold, suspicious', 'warm, inviting' etc.")
    text: str = Field(description="The actual line of dialogue or narration")
    voice_suggestion: str = Field(description="For NEW characters, suggest a voice from the provided list (e.g. 'Zephyr', 'Puck'). Leave empty if unknown or NARRATOR.", default="")
    audio_url: str = Field(description="Leave empty. Populated by system.", default="")


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

## VOICE SELECTION
- For **NEW** characters (speakers other than NARRATOR that are not in the 'Known Voices' list), you MUST select a fitting voice from the 'Voice Options' list.
- Use the `voice_suggestion` field to specify this voice name.
- Consider the character's archetype, age, and vibe when choosing.
- **Voice Options**: {voice_options}
- **Known Voices**: {known_voices}

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
    # 1. Load Voice Data
    voices_path = os.path.join(base_dir, "data", "voice_options.json")
    char_voices_path = os.path.join(base_dir, "data", "character_voices.json")
    
    with open(voices_path, 'r') as f:
        voice_data = json.load(f)
        voice_list = ", ".join([f"{v['voice_name']} ({v.get('gender', 'unknown')})" for v in voice_data['voice_options']])
        
    known_voices = {}
    if os.path.exists(char_voices_path):
        with open(char_voices_path, 'r') as f:
            known_voices = json.load(f)
    
    known_voices_str = ", ".join([f"{k}: {v}" for k, v in known_voices.items()])

    # 2. Invoke Chain
    result = narrator_chain.invoke({
        "director_event": json.dumps(director_event, indent=2),
        "format_instructions": narrator_parser.get_format_instructions(),
        "voice_options": voice_list,
        "known_voices": known_voices_str
    })
    
    # 3. Post-Process for Audio (TTS)
    final_scene = process_scene_audio(result)
    
    return final_scene


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
def process_scene_audio(scene: dict) -> dict:
    """
    Generates audio for character lines using Gemini TTS.
    Updates the scene dict with audio_urls.
    Persists new voice assignments.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[TTS] No GOOGLE_API_KEY or GEMINI_API_KEY found. Skipping TTS.")
        return scene

    client = genai.Client(api_key=api_key)
    
    char_voices_path = os.path.join(base_dir, "data", "character_voices.json")
    static_audio_dir = os.path.join(base_dir, "static", "audio")
    os.makedirs(static_audio_dir, exist_ok=True)
    
    # Load persistence
    known_voices = {}
    if os.path.exists(char_voices_path):
        with open(char_voices_path, 'r') as f:
            known_voices = json.load(f)
            
    voices_updated = False
    
    # Load voice options for gender lookup
    voices_path = os.path.join(base_dir, "data", "voice_options.json")
    voice_gender_map = {}
    if os.path.exists(voices_path):
        with open(voices_path, 'r') as f:
            v_data = json.load(f)
            for v in v_data.get('voice_options', []):
                voice_gender_map[v['voice_name']] = v.get('gender', 'Unknown')

    for line in scene.get('scene', []):
        speaker = line.get('speaker', 'NARRATOR')
        text = line.get('text', '')
        style = line.get('style', '')
        suggestion = line.get('voice_suggestion', '')
        
        # Skip Narrator (for now, unless we want a narrator voice)
        if speaker == "NARRATOR":
            continue
            
        # Determine Voice
        voice_name = known_voices.get(speaker)
        
        if not voice_name:
            if suggestion:
                voice_name = suggestion
                known_voices[speaker] = voice_name
                voices_updated = True
                print(f"[TTS] New voice assigned: {speaker} -> {voice_name}")
            else:
                # Fallback if no suggestion
                voice_name = "Schedar" # Default fallback (Even, Male)
        


        # Generate Audio
        try:
            tts_prompt = text
            
            from utils.settings_manager import get_setting
            tts_model = get_setting("narrator_tts_model", "gemini-2.5-flash-preview-tts")

            response = client.models.generate_content(
                model=tts_model,
                contents=tts_prompt,
                config={
                    'response_modalities': ['AUDIO'],
                    'speech_config': {
                        'voice_config': {
                            'prebuilt_voice_config': {
                                'voice_name': voice_name
                            }
                        }
                    }
                }
            )
            
            
            audio_bytes = None
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                         audio_bytes = part.inline_data.data
            
            if audio_bytes:
                filename = f"{uuid.uuid4()}.wav"
                filepath = os.path.join(static_audio_dir, filename)
                
                # Gemini TTS output is raw PCM: 24kHz, 1 channel, 16-bit (2 bytes)
                import wave
                with wave.open(filepath, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    wav_file.writeframes(audio_bytes)
                
                # Set URL
                line['audio_url'] = f"/static/audio/{filename}"
            else:
                print(f"[TTS] No audio data received for {speaker}.")
        
        except Exception as e:
            print(f"[TTS] Error generating audio for {speaker}: {e}")

    # Save assignments if changed
    if voices_updated:
        with open(char_voices_path, 'w') as f:
            json.dump(known_voices, f, indent=2)

    return scene


def speak_scene(scene: dict) -> None:
    """
    Process scene for display (and now the audio is already processed).
    """
    print("\n--- SCENE ---")
    for line in scene.get('scene', []):
        speaker = line.get('speaker', 'NARRATOR')
        style = line.get('style', '')
        text = line.get('text', '')
        audio = line.get('audio_url', '')
        
        if speaker == "NARRATOR":
            print(f"\n[NARRATOR] ({style}):\n  {text}\n")
        else:
            audio_icon = "[AUDIO]" if audio else ""
            print(f"  [{speaker}] ({style}) {audio_icon}: \"{text}\"")
    
    print("--- END SCENE ---\n")

