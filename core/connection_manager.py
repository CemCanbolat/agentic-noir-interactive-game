import json
import uuid
from typing import List, Dict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.players: Dict[str, Dict] = {}
        self.inactive_players: Dict[str, Dict] = {}  # Store disconnected player info
        self.last_scene_data: List[Dict] = []    # Store last scene for sync

    async def connect(self, websocket: WebSocket, player_id: str = None) -> str:
        await websocket.accept()
        
        # 1. Try to restore existing player
        if player_id and (player_id in self.players or player_id in self.inactive_players):
            if player_id in self.inactive_players:
                # Restore from inactive
                self.players[player_id] = self.inactive_players.pop(player_id)
                self.players[player_id]["ws"] = websocket
                print(f"Player {player_id} reconnected (restored).")
            elif player_id in self.players:
                # Phantom connection or multiple tabs - update WS
                # Close old WS if open? For now just overwrite.
                try:
                    await self.players[player_id]["ws"].close()
                except:
                    pass
                self.players[player_id]["ws"] = websocket
                print(f"Player {player_id} reconnected (active session).")
        else:
            # 2. New player
            player_id = str(uuid.uuid4())[:8]
            self.players[player_id] = {"ws": websocket, "nickname": None, "ready": False, "has_nickname": False}
            print(f"Player {player_id} connected (new).")

        # Always send ID confirmation
        await websocket.send_text(json.dumps({"type": "assign_id", "player_id": player_id}))
        await self.broadcast_player_list()
        return player_id

    async def disconnect(self, player_id: str, websocket: WebSocket):
        if player_id in self.players:
            # Race condition check: Only disconnect if this is the ACTIVE socket
            if self.players[player_id]["ws"] != websocket:
                print(f"Ignored disconnect for player {player_id} (socket mismatch - phantom disconnect).")
                return

            # Move to inactive instead of deleting
            player_data = self.players.pop(player_id)
            player_data["ws"] = None # Remove WS object
            self.inactive_players[player_id] = player_data
            print(f"Player {player_id} disconnected (moved to inactive).")
        await self.broadcast_player_list()

    async def set_nickname(self, player_id: str, nickname: str):
        if player_id in self.players:
            self.players[player_id]["nickname"] = nickname
            self.players[player_id]["has_nickname"] = True
            # Don't auto-set ready anymore, player needs to click Ready button
            print(f"Player {player_id} set nickname: {nickname}")
            await self.broadcast_player_list()
            await self.broadcast_system(f"{nickname} joined the case.")

    async def toggle_ready(self, player_id: str) -> bool:
        """Toggle ready state for a player. Returns new ready state."""
        if player_id in self.players and self.players[player_id]["nickname"]:
            new_state = not self.players[player_id]["ready"]
            self.players[player_id]["ready"] = new_state
            nickname = self.players[player_id]["nickname"]
            print(f"Player {player_id} ({nickname}) ready: {new_state}")
            await self.broadcast_player_list()
            return new_state
        return False

    def check_all_ready(self) -> tuple[bool, int, int]:
        """Check if all players with nicknames are ready.
        Returns (all_ready, ready_count, total_with_nicknames)"""
        players_with_names = [p for p in self.players.values() if p.get("nickname")]
        if not players_with_names:
            return False, 0, 0
        ready_count = sum(1 for p in players_with_names if p.get("ready"))
        total = len(players_with_names)
        return ready_count == total, ready_count, total

    async def broadcast_countdown(self, count: int):
        """Broadcast countdown message to all players."""
        message = json.dumps({"type": "countdown", "count": count})
        for info in self.players.values():
            try:
                await info["ws"].send_text(message)
            except:
                pass

    async def reset_all_ready(self):
        """Reset ready state for all players (e.g., when returning to lobby)."""
        for player_id in self.players:
            self.players[player_id]["ready"] = False
        for player_id in self.inactive_players:
            self.inactive_players[player_id]["ready"] = False
        await self.broadcast_player_list()

    def get_player_list(self) -> dict:
        """Get sanitized player list for broadcasting."""
        active = {
            pid: {"nickname": info["nickname"], "ready": info["ready"], "status": "online"}
            for pid, info in self.players.items()
        }
        inactive = {
             pid: {"nickname": info["nickname"], "ready": info["ready"], "status": "offline"}
             for pid, info in self.inactive_players.items()
             if info["nickname"] # Only show if they had a name
        }
        return {**active, **inactive}

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
        sender_info = self.players.get(sender_id)
        if not sender_info: return 
        
        sender_name = sender_info.get("nickname") or f"Detective-{sender_id[-3:]}"
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
        self.last_scene_data = scene # Store for sync
        for info in self.players.values():
            try:
                await info["ws"].send_text(json.dumps({"type": "scene", "data": scene}))
            except:
                pass

    async def send_game_state(self, player_id: str):
        """Send current game state to a specific player (late join/reconnect)."""
        if player_id not in self.players:
            return
            
        ws = self.players[player_id]["ws"]
        try:
            # 1. Send Game Started signal if needed
            # (We don't strictly know if game started here, but this is usually called if it has)
            # Fetch intro text to be safe
            intro_text = "The case continues..." # Simplified for reconnect
            
            await ws.send_text(json.dumps({
                "type": "game_started",
                "case": "iris_bell", # TODO: Get from GameState if dynamic
                "intro": None, # Don't replay intro text for reconnects usually, or maybe do?
                "intro_audio_url": None
            }))
            
            # 2. Send last scene
            if self.last_scene_data:
                 await ws.send_text(json.dumps({"type": "scene", "data": self.last_scene_data}))
            
            # 3. Send system message
            await ws.send_text(json.dumps({"type": "system", "text": "Reconnected to ongoing investigation."}))
                 
        except Exception as e:
            print(f"Error syncing player {player_id}: {e}")

    async def broadcast_game_start(self, case_id: str):
        """Notify all players that the game has started."""
        # Load intro from file if available
        intro_text = "The case begins..."
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        intro_path = os.path.join(base_dir, "scripts", "intro_story.txt")
        
        if os.path.exists(intro_path):
            with open(intro_path, "r", encoding="utf-8") as f:
                intro_text = f.read().strip()
        else:
             intro_messages = {
                "iris_bell": "The rain hammers against your fedora as you push through the doors of The Silver Gull. A torch singer lies dead in her dressing room. Three suspects, one truth. Time to work."
            }
             intro_text = intro_messages.get(case_id, "The case begins...")

        
        message = json.dumps({
            "type": "game_started",
            "case": case_id,
            "intro": intro_text,
            "intro_audio_url": "/static/audio/intro.wav"
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
