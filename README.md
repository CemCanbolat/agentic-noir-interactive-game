# Agentic Noir 🕵️‍♂️🌧️

**Agentic Noir** is a collaborative, interactive detective game set in a gritty 1940s film noir universe. Players step into the shoes of a hard-boiled detective to solve the murder of torch singer Iris Bell.

Key Features:

- **Multiplayer Lobby**: Team up with other detectives in real-time.
- **AI-Driven Storytelling**: No pre-written scripts. The story evolves dynamically based on your actions.
- **Atmospheric Immersion**: Experience the rain-soaked streets of Greywater City through rich, procedurally generated narrative.

## How it Works: The Multi-Agent Flow 🤖

The game is powered by a pipeline of specialized AI agents that work together to create a cohesive experience:

1.  **The Director (Game Master)** 🎬
    - Analyzes player input (e.g., "Look under the rug", "Ask the bartender about the gun").
    - Manages the **World State**: Tracks inventory, discovered clues, visited locations, and suspect relationships.
    - Decides the _logical_ outcome of an action (Success/Failure, Item Found, Info Revealed).
    - Passes a structured "Narrative Event" to the Narrator.

2.  **The Narrator (Storyteller)** 🖊️
    - Receives the dry facts from the Director.
    - Transforms them into atmospheric, noir-style prose.
    - Generates dialogue for NPCs (suspects, witnesses) in character.
    - Streams the final scene back to the players.

This separation ensures the game remains logically consistent (Director) while providing a rich, literary experience (Narrator).

## Getting Started

1.  **Install Dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the Server**:

    ```bash
    python main.py
    ```

3.  **Play**:
    Open `http://localhost:8000` in your browser.
