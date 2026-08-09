import asyncio
import json
import logging
import threading
import websockets

logger = logging.getLogger(__name__)

# Global state & clients storage
_CONNECTED_CLIENTS = set()
_CURRENT_STATE = "idle"
_EVENT_LOOP = None

def broadcast_state(state_value: str, text: str = ""):
    """Broadcast state update ('idle', 'listening', 'thinking', 'speaking') to all connected 3D UI clients."""
    global _CURRENT_STATE, _EVENT_LOOP
    _CURRENT_STATE = state_value
    msg = json.dumps({"type": "state", "value": state_value, "text": text})
    _async_broadcast(msg)

def broadcast_response(text: str):
    """Broadcast assistant spoken/generated response text to 3D UI HUD."""
    msg = json.dumps({"type": "assistant_response", "text": text})
    _async_broadcast(msg)

def _async_broadcast(message_str: str):
    if _EVENT_LOOP and _EVENT_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(_send_to_all(message_str), _EVENT_LOOP)

async def _send_to_all(message_str: str):
    if _CONNECTED_CLIENTS:
        # Create tasks for all connected clients
        tasks = [asyncio.create_task(client.send(message_str)) for client in list(_CONNECTED_CLIENTS)]
        await asyncio.gather(*tasks, return_exceptions=True)

async def _handle_ws_connection(websocket, path=None):
    _CONNECTED_CLIENTS.add(websocket)
    logger.info(f"[WebSocket Bridge] 3D HUD Client connected: {websocket.remote_address}")
    
    # Send current state upon connection
    try:
        await websocket.send(json.dumps({"type": "state", "value": _CURRENT_STATE}))
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "gesture_command":
                    cmd = data.get("value")
                    logger.info(f"[WebSocket Bridge] Received gesture command: {cmd}")
                    _handle_gesture_command(cmd, data)
            except Exception as e:
                logger.warning(f"[WebSocket Bridge] Message handling error: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        _CONNECTED_CLIENTS.remove(websocket)
        logger.info(f"[WebSocket Bridge] 3D HUD Client disconnected.")

def _handle_gesture_command(command: str, payload: dict):
    """Process hand gesture command sent from 3D renderer."""
    if command == "activate":
        print("🖐️ [GESTURE ACTIVATED] Open Palm detected -> Triggering Assistant Listening Mode!")
        broadcast_state("listening", "Listening to Rupankar Sir...")
    elif command == "idle":
        print("✊ [GESTURE STANDBY] Closed Fist detected -> Assistant in Standby Mode!")
        broadcast_state("idle")
    elif command == "next":
        print("👉 [GESTURE SWIPE RIGHT] Next command triggered!")
        broadcast_state("thinking", "Processing next action...")
    elif command == "dismiss":
        print("👈 [GESTURE SWIPE LEFT] Dismiss triggered!")
        broadcast_state("idle")
    elif command == "volume":
        vol = payload.get("data", {}).get("level", 50)
        print(f"👌 [GESTURE PINCH] Adjusting volume level: {vol}%")

async def _start_ws_server_async(host="localhost", port=8765):
    global _EVENT_LOOP
    _EVENT_LOOP = asyncio.get_running_loop()
    async with websockets.serve(_handle_ws_connection, host, port):
        logger.info(f"🚀 [WebSocket Bridge] Server listening on ws://{host}:{port}")
        await asyncio.Future()  # run forever

def start_websocket_bridge(host="localhost", port=8765):
    """Launch WebSocket bridge server in a background daemon thread."""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_start_ws_server_async(host, port))

    t = threading.Thread(target=_run, daemon=True, name="JarvisWebSocketBridge")
    t.start()
    print(f"🚀 [WEBSOCKET BRIDGE STARTED] ws://{host}:{port}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing WebSocket Bridge Standalone...")
    start_websocket_bridge()
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("Bridge stopped.")
