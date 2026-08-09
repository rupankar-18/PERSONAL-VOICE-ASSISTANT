/**
 * MediaPipe Hands Real-Time Gesture Recognition & Smoothing Layer
 * Maps 21 Hand Landmarks to 3D Iron Man Orb & Assistant Commands
 */

class GestureController {
  constructor() {
    this.videoElement = document.getElementById('webcam-video');
    this.canvasElement = document.getElementById('landmark-canvas');
    this.canvasCtx = this.canvasElement.getContext('2d');

    // Exponential Moving Average (EMA) smoothed landmarks per hand
    this.smoothedLandmarks = [];
    this.lerpFactor = 0.22; // Smooths jitter while keeping response fast

    // State debouncing
    this.activeGesture = 'None';
    this.gestureHoldTime = 0;
    this.lastGesture = 'None';
    this.holdThreshold = 150; // ms required to confirm discrete gesture

    // Swipe tracking variables
    this.lastPalmX = null;
    this.swipeCooldown = 0;

    this.showOverlay = true;

    this.initMediaPipe();
  }

  initMediaPipe() {
    if (typeof Hands === 'undefined') {
      console.warn('[Gestures] MediaPipe Hands CDN loading...');
      setTimeout(() => this.initMediaPipe(), 1000);
      return;
    }

    this.hands = new Hands({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
    });

    this.hands.setOptions({
      maxNumHands: 2,
      modelComplexity: 1,
      minDetectionConfidence: 0.6,
      minTrackingConfidence: 0.6
    });

    this.hands.onResults((results) => this.onResults(results));

    this.camera = new Camera(this.videoElement, {
      onFrame: async () => {
        await this.hands.send({ image: this.videoElement });
      },
      width: 640,
      height: 480
    });

    this.camera.start().then(() => {
      console.log('🎥 [Gestures] Webcam hand tracking started.');
    }).catch(err => {
      console.error('❌ [Gestures] Webcam access error:', err);
    });
  }

  onResults(results) {
    this.canvasCtx.save();
    this.canvasCtx.clearRect(0, 0, this.canvasElement.width, this.canvasElement.height);

    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      this.activeGesture = 'None';
      this.updateUI();
      this.canvasCtx.restore();
      return;
    }

    // Apply EMA smoothing across multi-hand landmarks
    const rawHands = results.multiHandLandmarks;
    this.smoothLandmarks(rawHands);

    // Render landmark skeleton on debug canvas if visible
    if (this.showOverlay) {
      for (const landmarks of this.smoothedLandmarks) {
        this.drawHandOverlay(landmarks);
      }
    }

    // Process Hand Gestures
    this.processGestures(this.smoothedLandmarks);

    this.canvasCtx.restore();
  }

  smoothLandmarks(rawHands) {
    if (this.smoothedLandmarks.length !== rawHands.length) {
      this.smoothedLandmarks = JSON.parse(JSON.stringify(rawHands));
      return;
    }

    for (let h = 0; h < rawHands.length; h++) {
      const rawPoints = rawHands[h];
      const smoothPoints = this.smoothedLandmarks[h];

      for (let i = 0; i < rawPoints.length; i++) {
        smoothPoints[i].x += (rawPoints[i].x - smoothPoints[i].x) * this.lerpFactor;
        smoothPoints[i].y += (rawPoints[i].y - smoothPoints[i].y) * this.lerpFactor;
        smoothPoints[i].z += (rawPoints[i].z - smoothPoints[i].z) * this.lerpFactor;
      }
    }
  }

  processGestures(hands) {
    const now = performance.now();
    let detectedGesture = 'None';

    if (hands.length === 2) {
      // TWO HAND GESTURES: Pull Apart (Expand) / Push Together (Contract)
      const hand1Palm = hands[0][0]; // Wrist landmark
      const hand2Palm = hands[1][0];

      const dist = Math.hypot(hand1Palm.x - hand2Palm.x, hand1Palm.y - hand2Palm.y);

      // Normal dist ~0.4 -> Scale 1.0; dist 0.8 -> Scale 1.8; dist 0.15 -> Scale 0.6
      const targetScale = Math.min(2.2, Math.max(0.5, dist * 2.8));
      const targetSpread = Math.min(2.0, Math.max(0.6, dist * 2.5));

      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(targetScale, undefined, undefined, targetSpread);
      }

      detectedGesture = dist > 0.5 ? 'Two Fists (Expand Orb)' : 'Two Fists (Contract Orb)';

    } else if (hands.length === 1) {
      // SINGLE HAND GESTURES
      const lm = hands[0];

      const isOpenPalm = this.checkOpenPalm(lm);
      const isFist = this.checkClosedFist(lm);
      const isPinch = this.checkPinch(lm);

      // Single Hand Wrist Rotation
      const wrist = lm[0];
      const middleKnuckle = lm[9];
      const rotY = (wrist.x - 0.5) * Math.PI * 2.0;
      const rotX = (wrist.y - 0.5) * Math.PI;

      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(undefined, rotX, rotY, undefined);
      }

      // Check Swipe Motion
      if (now > this.swipeCooldown) {
        if (this.lastPalmX !== null) {
          const deltaX = wrist.x - this.lastPalmX;
          if (deltaX < -0.12) {
            detectedGesture = 'Swipe Right (Next)';
            this.sendGestureCommand('next');
            this.swipeCooldown = now + 800;
          } else if (deltaX > 0.12) {
            detectedGesture = 'Swipe Left (Dismiss)';
            this.sendGestureCommand('dismiss');
            this.swipeCooldown = now + 800;
          }
        }
        this.lastPalmX = wrist.x;
      }

      if (detectedGesture === 'None') {
        if (isOpenPalm) {
          detectedGesture = 'Open Palm (Listen)';
          if (jarvisOrb && jarvisOrb.state !== 'listening') {
            jarvisOrb.setState('listening');
            this.sendGestureCommand('activate');
          }
        } else if (isFist) {
          detectedGesture = 'Closed Fist (Idle)';
          if (jarvisOrb && jarvisOrb.state !== 'idle') {
            jarvisOrb.setState('idle');
            this.sendGestureCommand('idle');
          }
        } else if (isPinch.active) {
          detectedGesture = `Pinch (Volume ${isPinch.volume}%)`;
          this.sendGestureCommand('volume', { level: isPinch.volume });
        }
      }
    }

    this.activeGesture = detectedGesture;
    this.updateUI();
  }

  checkOpenPalm(lm) {
    // Open Palm: All fingertips (4, 8, 12, 16, 20) are extended above their PIP knuckles
    return (
      lm[8].y < lm[6].y &&  // Index
      lm[12].y < lm[10].y && // Middle
      lm[16].y < lm[14].y && // Ring
      lm[20].y < lm[18].y    // Pinky
    );
  }

  checkClosedFist(lm) {
    // Closed Fist: All fingertips (8, 12, 16, 20) curled below MCP knuckles
    return (
      lm[8].y > lm[6].y &&
      lm[12].y > lm[10].y &&
      lm[16].y > lm[14].y &&
      lm[20].y > lm[18].y
    );
  }

  checkPinch(lm) {
    // Pinch distance between Thumb Tip (4) and Index Tip (8)
    const dist = Math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y);
    const isPinch = dist < 0.07;
    const volPct = Math.round(Math.min(100, Math.max(0, (0.2 - dist) * 700)));

    return { active: isPinch, volume: volPct };
  }

  sendGestureCommand(cmdValue, dataObj = {}) {
    if (window.jarvisApp && window.jarvisApp.ws) {
      window.jarvisApp.sendWebSocketMessage({
        type: 'gesture_command',
        value: cmdValue,
        data: dataObj
      });
    }
  }

  drawHandOverlay(lm) {
    const ctx = this.canvasCtx;
    const w = this.canvasElement.width;
    const h = this.canvasElement.height;

    ctx.strokeStyle = '#00f3ff';
    ctx.fillStyle = '#ff8800';
    ctx.lineWidth = 1.5;

    // Draw connection lines
    const connections = [
      [0,1],[1,2],[2,3],[3,4],
      [0,5],[5,6],[6,7],[7,8],
      [5,9],[9,10],[10,11],[11,12],
      [9,13],[13,14],[14,15],[15,16],
      [13,17],[17,18],[18,19],[19,20],[0,17]
    ];

    for (const [p1, p2] of connections) {
      ctx.beginPath();
      ctx.moveTo((1 - lm[p1].x) * w, lm[p1].y * h);
      ctx.lineTo((1 - lm[p2].x) * w, lm[p2].y * h);
      ctx.stroke();
    }

    // Draw points
    for (let i = 0; i < lm.length; i++) {
      ctx.beginPath();
      ctx.arc((1 - lm[i].x) * w, lm[i].y * h, 3, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  updateUI() {
    const gestureEl = document.getElementById('gesture-name');
    const scaleEl = document.getElementById('orb-scale-val');

    if (gestureEl) gestureEl.textContent = this.activeGesture;
    if (scaleEl && jarvisOrb) scaleEl.textContent = jarvisOrb.scale.toFixed(2);
  }
}

function toggleDebugOverlay() {
  const canvas = document.getElementById('landmark-canvas');
  if (canvas) canvas.classList.toggle('hidden');
}

let gestureController = null;
document.addEventListener('DOMContentLoaded', () => {
  gestureController = new GestureController();
});
