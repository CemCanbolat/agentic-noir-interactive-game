
import os
import json
import uuid
import wave
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from google import genai

# Load environment variables
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

def load_solution():
    solution_path = os.path.join(base_dir, "data", "solution.json")
    with open(solution_path, 'r') as f:
        return json.load(f)

def generate_intro_text(solution):
    """Generates the intro text using a high-end GPT model."""
    
    # Extract non-spoiler context
    victim = solution.get("victim", {}).get("name")
    crime_scene = solution.get("crime_scene")
    known_locations = ", ".join(solution.get("known_locations", []))
    
    system_prompt = """
    You are the Narrator of a gritty, atmospheric film noir detective story set in 1947.
    Your task is to write a short opening monologue (approx. 80-120 words) that sets the mood and introduces the scene.
    
    **Tone:** Dark, cynical, poetic, hard-boiled. Use sensory details (rain, smoke, shadows).
    **Context:** 
    - The location is: {crime_scene}
    - The victim is: {victim}
    - Other known locations in the city: {known_locations}
    
    **CRITICAL RULES:**
    1. Do NOT reveal the killer ({culprit}).
    2. Do NOT reveal specific key clues or the solution.
    3. Focus on the atmosphere, the city, and the discovery of the body.
    4. Write in the second person ("You stand over the body...", "The rain hits your trench coat...").
    5. Ending: End with a hook that invites the detective (the player) to start investigating.
    """
    
    human_prompt = "Generate the opening narration."
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    
    # "Higher model GPT" -> GPT-4o
    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    except Exception:
        print("Fallback to gpt-4o-mini if gpt-4o is unavailable/erroring")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    chain = prompt | llm | StrOutputParser()
    
    culprit = solution.get("culprit")
    
    text = chain.invoke({
        "crime_scene": crime_scene,
        "victim": victim,
        "known_locations": known_locations,
        "culprit": culprit
    })
    
    return text

def generate_intro_audio(text, output_path):
    """Generates audio using Gemini TTS."""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: No GEMINI_API_KEY or GOOGLE_API_KEY found.")
        return

    client = genai.Client(api_key=api_key)
    
    # Voice selection: Algenib (Gravelly, Male) is perfect for Noir
    voice_name = "Algenib"
    
    print(f"Generating audio with Gemini TTS (Voice: {voice_name})...")
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro-preview-tts",
            contents=text,
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
            # Gemini TTS output is raw PCM: 24kHz, 1 channel, 16-bit (2 bytes)
            # Save as WAV for playability
            with wave.open(output_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(audio_bytes)
            print(f"Audio saved to: {output_path}")
        else:
            print("Error: No audio data received from Gemini.")

    except Exception as e:
        print(f"Error generating audio: {e}")

def main():
    print("Loading solution data...")
    solution = load_solution()
    
    print("Generating intro text...")
    intro_text = generate_intro_text(solution)
    
    print("\n--- Generated Intro ---")
    print(intro_text)
    print("-----------------------\n")
    
    # Save text
    text_path = os.path.join(base_dir, "scripts", "intro_story.txt")
    with open(text_path, "w") as f:
        f.write(intro_text)
    print(f"Text saved to: {text_path}")
    
    # Generate Audio
    audio_path = os.path.join(base_dir, "scripts", "intro_audio.wav")
    generate_intro_audio(intro_text, audio_path)
    
    print("Done!")

if __name__ == "__main__":
    main()
