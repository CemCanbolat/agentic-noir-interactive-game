import json
import uuid
import os
import asyncio
from typing import List, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv


# === 1. AGENT & HELPER IMPORTS ===
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# Import your agent chains and parsers
from agents.director import director_chain, director_parser
from agents.narrator import narrator_chain, narrator_parser

app = FastAPI()

# === 2. DATA HELPER FUNCTIONS ===
from utils import load_json_data, save_json_data

# === 3. MODIFIED CONNECTION MANAGER ===
class ConnectionManager:
    def __init__(self):
        self.players: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        player_id = str(uuid.uuid4())[:8]
        self.players[player_id] = {"ws": websocket, "nickname": None}
        await websocket.send_text(json.dumps({"type": "assign_id", "player_id": player_id}))
        print(f"Player {player_id} connected.")
        return player_id

    def disconnect(self, player_id: str):
        self.players.pop(player_id, None)
        print(f"Player {player_id} disconnected.")

    async def set_nickname(self, player_id: str, nickname: str):
        if player_id in self.players:
            self.players[player_id]["nickname"] = nickname
            await self.broadcast_system(f"{nickname} joined the case.")
            print(f"Player {player_id} set nickname: {nickname}")

    async def broadcast(self, sender_id: str, message: str):
        sender_name = self.players[sender_id]["nickname"] or f"Detective-{sender_id[-3:]}"
        for pid, info in self.players.items():
            tag = "You" if pid == sender_id else sender_name
            await info["ws"].send_text(json.dumps({"type": "chat", "sender": tag, "text": message}))

    async def broadcast_system(self, message: str):
        for info in self.players.values():
            await info["ws"].send_text(json.dumps({"type": "system", "text": message}))

    async def broadcast_scene(self, scene: List[Dict]):
        """Broadcasts the structured scene data to all connected players."""
        for info in self.players.values():
            await info["ws"].send_text(json.dumps({"type": "scene", "data": scene}))

manager = ConnectionManager()

# === 4. AGENT GAME LOOP ===
def run_game_turn_sync(player_action: str) -> (dict, dict):
    """
    Runs the full Director > Narrator agent pipeline.
    This is a BLOCKING (synchronous) function.
    """
    # 1. Load state
    world_state = load_json_data('data/world_state.json')
    solution = load_json_data('data/solution.json')

    # 2. Run Director
    print("Director is thinking...")
    director_decision = director_chain.invoke({
        "solution": json.dumps(solution),
        "world_state": json.dumps(world_state),
        "action": player_action,
        "format_instructions": director_parser.get_format_instructions()
    })

    # 3. Run Narrator
    print("Narrator is writing...")
    narrator_output = narrator_chain.invoke({
        "director_command": director_decision['narrator_prompt'],
        "format_instructions": narrator_parser.get_format_instructions()
    })

    # 4. Update and save state
    world_state['current_location'] = director_decision['new_location']
    world_state['progress'] = director_decision['progress_update']
    world_state['discovered_clues'] = list(set(world_state['discovered_clues'] + director_decision['clues_discovered']))
    world_state['interviewed_suspects'] = list(set(world_state.get('interviewed_suspects', []) + director_decision.get('interviewed_suspects', [])))
    
    save_json_data('data/world_state.json', world_state)
    print("World state updated.")

    return director_decision, narrator_output

# === 5. MODIFIED WEBSOCKET ENDPOINT ===
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    player_id = await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            if payload["type"] == "nickname":
                await manager.set_nickname(player_id, payload["nickname"])
            
            elif payload["type"] == "chat":

                player_action = payload["text"]
                
                # 1. Broadcast the player's action so everyone sees it
                await manager.broadcast(player_id, player_action)
                
                # 2. Run the game loop in a separate thread to avoid blocking the server.
                director_decision, narrator_output = await asyncio.to_thread(
                    run_game_turn_sync, player_action
                )

                # 3. Broadcast the Narrator's scene to everyone
                await manager.broadcast_scene(narrator_output['scene'])

                # 4. Broadcast the new interactables as a system message
                if director_decision['interactable_list']:
                    interact_list_str = ", ".join(director_decision['interactable_list'])
                    await manager.broadcast_system(f"Interactable: {interact_list_str}")

    except WebSocketDisconnect:
        manager.disconnect(player_id)
    except Exception as e:
        print(f"An error occurred in websocket: {e}")
        manager.disconnect(player_id)


# === 6. MODIFIED HTML/JS CLIENT ===
@app.get("/")
async def get():
    html = """
    <!DOCTYPE html>
    <html style="background-color: #1a1a1a; color: #e0e0e0;">
    <head>
        <title>Agentic Noir</title>
        <style>
            body { font-family: 'Consolas', 'Courier New', monospace; max-width: 800px; margin: 20px auto; }
            h3 { color: #ffc107; }
            #log {
                width: 100%;
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 10px;
                box-sizing: border-box;
                border-radius: 4px;
                font-family: inherit;
            }
            #msg {
                width: 70%;
                padding: 8px;
                border: 1px solid #555;
                background-color: #3b3b3b;
                color: #e0e0e0;
                border-radius: 4px;
            }
            button {
                padding: 8px 12px;
                background-color: #ffc107;
                color: #1a1a1a;
                border: none;
                cursor: pointer;
                border-radius: 4px;
                font-weight: bold;
            }
            .chat-msg { color: #ffffff; }
            .scene-narrator { color: #a9a9a9; font-style: italic; }
            .scene-npc { color: #ffc107; font-weight: bold; }
            .scene-style { color: #999; font-size: 0.9em; }
            .system-msg { color: #00bcd4; font-style: italic; }
        </style>
    </head>
    <body>
        <h3>🕵️ Agentic Noir</h3>
        <div id="idLabel">Connecting...</div>
        <textarea id="log" rows="20" cols="80" readonly></textarea><br>
        <input id="msg" placeholder="Describe your action..." onkeydown="event.key === 'Enter' && sendMsg()" />
        <button onclick="sendMsg()">Send</button>

        <script>
            let ws = new WebSocket("ws://" + window.location.host + "/ws");
            let myID = null;
            let nickname = null;
            let log = document.getElementById('log');

            function addLog(message, cssClass) {
                log.value += message + "\\n";
                // This is a bit of a hack for a textarea, but it's an MVP!
                // A real app would use <div>s.
                // For now, we'll just add simple text.
            }
            
            function addSceneLog(speaker, style, text) {
                let prefix = `[${speaker}]`;
                if (speaker === "NARRATOR") {
                    log.value += `\\n[NARRATOR] (${style}): ${text}\\n\\n`;
                } else {
                     log.value += `  [${speaker}] (${style}): "${text}"\\n`;
                }
                log.scrollTop = log.scrollHeight;
            }

            ws.onmessage = (event) => {
                let data = JSON.parse(event.data);
                
                switch (data.type) {
                    case "assign_id":
                        myID = data.player_id;
                        nickname = prompt("Enter your detective name:");
                        if (!nickname) nickname = "Detective-" + myID.slice(-3);
                        ws.send(JSON.stringify({type: "nickname", nickname: nickname}));
                        document.getElementById("idLabel").innerText = "You are " + nickname;
                        break;
                    
                    case "system":
                        log.value += `[SYSTEM]: ${data.text}\\n`;
                        break;
                    
                    case "chat":
                        log.value += `[${data.sender}]: ${data.text}\\n`;
                        break;
                    
                    // === NEW: HANDLE THE SCENE ===
                    case "scene":
                        data.data.forEach(line => {
                            addSceneLog(line.speaker, line.style, line.text);
                        });
                        break;
                }
                log.scrollTop = log.scrollHeight; // Auto-scroll
            };

            function sendMsg() {
                let msg = document.getElementById('msg').value;
                if (msg) {
                    ws.send(JSON.stringify({type: "chat", text: msg}));
                    document.getElementById('msg').value = "";
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)