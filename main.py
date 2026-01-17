"""
Agentic Noir - Interactive Film Noir Detective Game
Main server with WebSocket multiplayer support and lobby system.
"""
import json
import uuid
import os
import asyncio
from typing import List, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# === 1. SETUP ===
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# Import agents and memory manager
from agents.director import invoke_director
from agents.narrator import invoke_narrator
from utils import memory_manager

app = FastAPI(title="Agentic Noir")


# === 2. GAME STATE ===
class GameState:
    """Global game state manager."""
    def __init__(self):
        self.in_lobby = True
        self.current_case = "iris_bell"
    
    def start_game(self, case_id: str = "iris_bell"):
        self.in_lobby = False
        self.current_case = case_id
        reset_game()
    
    def reset_to_lobby(self):
        self.in_lobby = True

game_state = GameState()


# === 3. DATA HELPER FUNCTIONS ===
def load_json_data(filepath: str) -> dict:
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, 'r') as f:
        return json.load(f)


def save_json_data(filepath: str, data: dict):
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, 'w') as f:
        json.dump(data, f, indent=4)


def reset_game():
    """Reset both world state and world memory for a new game."""
    template_path = os.path.join(base_dir, "data", "default_world_state.json")
    world_state_path = os.path.join(base_dir, "data", "world_state.json")
    try:
        with open(template_path, "r") as f:
            template_data = json.load(f)
        with open(world_state_path, "w") as f:
            json.dump(template_data, f, indent=4)
        print("World state reset to template.")
    except Exception as e:
        print(f"Failed to reset world state: {e}")
    
    memory_manager.reset_memory()
    print("World memory reset.")


# === 4. CONNECTION MANAGER ===
class ConnectionManager:
    def __init__(self):
        self.players: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        player_id = str(uuid.uuid4())[:8]
        self.players[player_id] = {"ws": websocket, "nickname": None, "ready": False}
        await websocket.send_text(json.dumps({"type": "assign_id", "player_id": player_id}))
        print(f"Player {player_id} connected.")
        await self.broadcast_player_list()
        return player_id

    async def disconnect(self, player_id: str):
        self.players.pop(player_id, None)
        print(f"Player {player_id} disconnected.")
        await self.broadcast_player_list()

    async def set_nickname(self, player_id: str, nickname: str):
        if player_id in self.players:
            self.players[player_id]["nickname"] = nickname
            self.players[player_id]["ready"] = True
            print(f"Player {player_id} set nickname: {nickname}")
            await self.broadcast_player_list()
            await self.broadcast_system(f"{nickname} joined the case.")

    def get_player_list(self) -> dict:
        """Get sanitized player list for broadcasting."""
        return {
            pid: {"nickname": info["nickname"], "ready": info["ready"]}
            for pid, info in self.players.items()
        }

    async def broadcast_player_list(self):
        """Send updated player list to all connected clients."""
        player_data = self.get_player_list()
        message = json.dumps({"type": "player_list", "players": player_data})
        for info in self.players.values():
            try:
                await info["ws"].send_text(message)
            except:
                pass

    async def broadcast(self, sender_id: str, message: str):
        sender_name = self.players[sender_id].get("nickname") or f"Detective-{sender_id[-3:]}"
        for pid, info in self.players.items():
            tag = "You" if pid == sender_id else sender_name
            await info["ws"].send_text(json.dumps({"type": "chat", "sender": tag, "text": message}))

    async def broadcast_system(self, message: str):
        for info in self.players.values():
            try:
                await info["ws"].send_text(json.dumps({"type": "system", "text": message}))
            except:
                pass

    async def broadcast_scene(self, scene: List[Dict]):
        for info in self.players.values():
            try:
                await info["ws"].send_text(json.dumps({"type": "scene", "data": scene}))
            except:
                pass

    async def broadcast_game_start(self, case_id: str):
        """Notify all players that the game has started."""
        intro_messages = {
            "iris_bell": "The rain hammers against your fedora as you push through the doors of The Silver Gull. A torch singer lies dead in her dressing room. Three suspects, one truth. Time to work."
        }
        intro = intro_messages.get(case_id, "The case begins...")
        
        message = json.dumps({
            "type": "game_started",
            "case": case_id,
            "intro": intro
        })
        for info in self.players.values():
            try:
                await info["ws"].send_text(message)
            except:
                pass

    async def broadcast_processing(self, is_processing: bool):
        """Notify all players about processing state."""
        message = json.dumps({"type": "processing", "status": is_processing})
        for info in self.players.values():
            try:
                await info["ws"].send_text(message)
            except:
                pass


manager = ConnectionManager()


# === 5. GAME LOOP ===
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


# === 6. WEBSOCKET ENDPOINT ===
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    player_id = await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            # Handle nickname setting (lobby)
            if payload["type"] == "nickname":
                await manager.set_nickname(player_id, payload["nickname"])
            
            # Handle game start request
            elif payload["type"] == "start_game":
                if game_state.in_lobby:
                    case_id = payload.get("case", "iris_bell")
                    game_state.start_game(case_id)
                    await manager.broadcast_game_start(case_id)
                    print(f"Game started: {case_id}")
            
            # Handle chat/actions (in-game)
            elif payload["type"] == "chat":
                if game_state.in_lobby:
                    continue  # Ignore chat in lobby
                
                player_action = payload["text"]
                await manager.broadcast(player_id, player_action)
                
                # Special commands
                if player_action.lower() == "/inventory":
                    items = memory_manager.get_inventory_items()
                    if items:
                        item_names = [f"- {item['name']}" for item in items]
                        await manager.broadcast_system("[Inventory]\n" + "\n".join(item_names))
                    else:
                        await manager.broadcast_system("[Inventory] Empty.")
                    continue
                
                if player_action.lower() == "/reset":
                    reset_game()
                    game_state.reset_to_lobby()
                    await manager.broadcast_system("[RESET] Game has been reset.")
                    await manager.broadcast_player_list()
                    continue
                
                if player_action.lower() == "/lobby":
                    game_state.reset_to_lobby()
                    await manager.broadcast_system("[LOBBY] Returning to lobby...")
                    continue
                
                # Run game turn
                try:
                    await manager.broadcast_processing(True)
                    director_decision, narrator_output = await asyncio.to_thread(
                        run_game_turn_sync, player_action
                    )
                    
                    await manager.broadcast_scene(narrator_output['scene'])
                    
                    if director_decision.get('interactables'):
                        interact_list = director_decision['interactables']
                        await manager.broadcast_system(f"[Interactable] {', '.join(interact_list)}")
                    
                except Exception as e:
                    print(f"Game turn error: {e}")
                    import traceback
                    traceback.print_exc()
                    await manager.broadcast_system("[Error] Something went wrong. Try again.")
                finally:
                    await manager.broadcast_processing(False)

    except WebSocketDisconnect:
        await manager.disconnect(player_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        import traceback
        traceback.print_exc()
        await manager.disconnect(player_id)


# === 7. REST ENDPOINTS ===
@app.post("/reset")
async def reset_endpoint():
    """API endpoint to reset the game."""
    reset_game()
    game_state.reset_to_lobby()
    return {"status": "reset", "message": "Game has been reset"}


@app.get("/state")
async def get_state():
    """Get current game state (for debugging)."""
    world_state = load_json_data('data/world_state.json')
    memory = memory_manager.load_memory()
    return {
        "in_lobby": game_state.in_lobby,
        "current_case": game_state.current_case,
        "players": manager.get_player_list(),
        "world_state": world_state,
        "memory": memory
    }


# === 8. STATIC FILES & HTML ===
@app.get("/")
async def get():
    """Serve the main game HTML from static folder."""
    static_path = os.path.join(base_dir, "static", "index.html")
    return FileResponse(static_path)


# === 9. STARTUP ===
@app.on_event("startup")
async def startup_event():
    """Initialize game state on server start."""
    print("[Agentic Noir] Server starting up...")
    reset_game()  # Reset world state and memory on every server start
    game_state.reset_to_lobby()
    print("[Agentic Noir] Server ready.")