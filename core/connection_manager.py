import json
import uuid
from typing import List, Dict
from fastapi import WebSocket

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
