"""
Agentic Noir - Interactive Film Noir Detective Game
Main server with WebSocket multiplayer support and lobby system.
"""
import json
import os
import asyncio
import uvicorn

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# === 1. SETUP ===
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

from utils import memory_manager
from utils.data_handler import load_json_data
from core.game_state import game_state, reset_game
from core.connection_manager import manager
from core.game_engine import run_game_turn_sync

app = FastAPI(title="Agentic Noir")


# === 2. WEBSOCKET ENDPOINT ===
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


# === 3. REST ENDPOINTS ===
@app.post("/reset")
async def reset_endpoint():
    """API endpoint to reset the game."""
    reset_game()
    game_state.reset_to_lobby()
    return {"status": "reset", "message": "Game has been reset"}


@app.get("/settings")
async def get_settings_endpoint():
    """Get current game settings."""
    from utils.settings_manager import load_settings
    return load_settings()


@app.post("/settings")
async def update_settings_endpoint(settings: dict):
    """Update game settings."""
    from utils.settings_manager import save_settings
    saved = save_settings(settings)
    return {"status": "success", "settings": saved}


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


# === 4. STATIC FILES & HTML ===
app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "static")), name="static")

@app.get("/")
async def get():
    """Serve the main game HTML from static folder."""
    static_path = os.path.join(base_dir, "static", "index.html")
    return FileResponse(static_path)


# === 5. STARTUP ===
@app.on_event("startup")
async def startup_event():
    """Initialize game state on server start."""
    print("[Agentic Noir] Server starting up...")
    reset_game()  # Reset world state and memory on every server start
    game_state.reset_to_lobby()
    print("[Agentic Noir] Server ready.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)