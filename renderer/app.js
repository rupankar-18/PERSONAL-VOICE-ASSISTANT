/**
 * Master Renderer Bridge App
 * Connects 3D Iron Man HUD to Python Assistant WebSocket Server (ws://localhost:8765)
 */

class JarvisApp {
  constructor() {
    this.wsHost = 'ws://localhost:8765';
    this.ws = null;
    this.connected = false;

    this.connectWebSocket();
  }

  connectWebSocket() {
    console.log(`🔌 [HUD Bridge] Connecting to Python Assistant WebSocket at ${this.wsHost}...`);

    try {
      this.ws = new WebSocket(this.wsHost);

      this.ws.onopen = () => {
        console.log('✅ [HUD Bridge] Connected to Python Assistant WebSocket!');
        this.connected = true;
        this.updateResponseBox('CONNECTED TO NEHA 3D JARVIS BACKEND');
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleServerMessage(data);
        } catch (err) {
          console.error('[HUD Bridge] Error parsing message:', err);
        }
      };

      this.ws.onclose = () => {
        console.warn('⚠️ [HUD Bridge] Disconnected from Python Assistant WebSocket. Retrying in 3s...');
        this.connected = false;
        setTimeout(() => this.connectWebSocket(), 3000);
      };

      this.ws.onerror = (err) => {
        console.error('[HUD Bridge] WebSocket error:', err);
      };

    } catch (e) {
      console.error('[HUD Bridge] Connection Exception:', e);
      setTimeout(() => this.connectWebSocket(), 3000);
    }
  }

  handleServerMessage(data) {
    if (data.type === 'state') {
      const stateVal = data.value;
      console.log(`[HUD Bridge] Assistant state updated: ${stateVal}`);

      if (jarvisOrb) {
        jarvisOrb.setState(stateVal);
      }

      if (data.text) {
        this.updateResponseBox(data.text);
      }
    } else if (data.type === 'assistant_response') {
      console.log(`[HUD Bridge] Assistant response: ${data.text}`);
      this.updateResponseBox(data.text);
    }
  }

  sendWebSocketMessage(obj) {
    if (this.ws && this.connected && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  updateResponseBox(text) {
    const box = document.getElementById('hud-response');
    if (box) {
      box.textContent = text;
      box.style.opacity = '1';
    }
  }
}

// Global initialization
window.jarvisApp = null;
document.addEventListener('DOMContentLoaded', () => {
  window.jarvisApp = new JarvisApp();
});