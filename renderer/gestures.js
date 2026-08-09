/**
 * MediaPipe Hands Ultra-Smooth Real-Time Gesture Recognition & Filter Layer
 * Velocity-Adaptive Low Pass Landmark Filtering + Precise Debounced Gesture Mapping
 */

class GestureController {
  constructor() {
    this.videoElement = document.getElementById('webcam-video');
    this.canvasElement = document.getElementById('landmark-canvas');
    this.canvasCtx = this.canvasElement.getContext('2d');

    // Smoothed landmarks & historical velocity tracking
    this.smoothedLandmarks = [];
    this.prevRawLandmarks = [];

    // Multi-frame state debouncing
    this.activeGesture = 'None';
    this.pendingGesture = 'None';
    this.pendingFrames = 0;
    this.REQUIRED_STABLE_FRAMES = 3; // 3 frames (~100ms) to confirm gesture switch

    // Swipe tracking buffer
    this.wristXBuffer = [];
    this.swipeCooldown = 0;

    this.showOverlay = true;

    this.initMediaPipe();
  }

  initMediaPipe() {
    if (typeof Hands === 'undefined') {
      console.warn('[Gestures] MediaPipe Hands CDN loading...');
      setTimeout(() => this.initMediaPipe(), 800);
      return;
    }

    this.hands = new Hands({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
    });

    this.hands.setOptions({
      maxNumHands: 2,
      modelComplexity: 1,
      minDetectionConfidence: 0.65,
      minTrackingConfidence: 0.65
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
      console.log('🎥 [Gestures] Webcam hand tracking started successfully.');
    }).catch(err => {
      console.error('❌ [Gestures] Webcam access error:', err);
    });
  }

  onResults(results) {
    this.canvasCtx.save();
    this.canvasCtx.clearRect(0, 0, this.canvasElement.width, this.canvasElement.height);

    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      this.activeGesture = 'None';
      this.pendingGesture = 'None';
      this.pendingFrames = 0;
      this.wristXBuffer = [];

      // Gently ease 3D orb back to default idle parameters when no hands in frame
      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(1.0, 0.0, 0.0, 1.0);
      }

      this.updateUI();
      this.canvasCtx.restore();
      return;
    }

    const rawHands = results.multiHandLandmarks;
    this.adaptiveSmoothLandmarks(rawHands);

    if (this.showOverlay) {
      for (const landmarks of this.smoothedLandmarks) {
        this.drawHandOverlay(landmarks);
      }
    }

    this.processGestures(this.smoothedLandmarks);

    this.canvasCtx.restore();
  }

  /**
   * Adaptive Velocity Low-Pass Filter (One Euro Filter approach)
   * High velocity -> lower smoothing (fast response)
   * Low velocity -> higher smoothing (zero jitter)
   */
  adaptiveSmoothLandmarks(rawHands) {
    if (this.smoothedLandmarks.length !== rawHands.length) {
      this.smoothedLandmarks = JSON.parse(JSON.stringify(rawHands));
      this.prevRawLandmarks = JSON.parse(JSON.stringify(rawHands));
      return;
    }

    for (let h = 0; h < rawHands.length; h++) {
      const rawPoints = rawHands[h];
      const smoothPoints = this.smoothedLandmarks[h];
      const prevPoints = this.prevRawLandmarks[h] || rawPoints;

      for (let i = 0; i < rawPoints.length; i++) {
        // Calculate instantaneous velocity
        const dx = rawPoints[i].x - prevPoints[i].x;
        const dy = rawPoints[i].y - prevPoints[i].y;
        const vel = Math.hypot(dx, dy);

        // Dynamic alpha lerp factor: 0.12 (slow/still) to 0.45 (rapid motion)
        const alpha = Math.min(0.45, Math.max(0.12, vel * 6.0));

        smoothPoints[i].x += (rawPoints[i].x - smoothPoints[i].x) * alpha;
        smoothPoints[i].y += (rawPoints[i].y - smoothPoints[i].y) * alpha;
        smoothPoints[i].z += (rawPoints[i].z - smoothPoints[i].z) * alpha;

        prevPoints[i] = { x: rawPoints[i].x, y: rawPoints[i].y, z: rawPoints[i].z };
      }
    }
  }

  processGestures(hands) {
    const now = performance.now();
    let detectedRaw = 'None';

    if (hands.length === 2) {
      // TWO HAND GESTURES: Dynamic Scale & Particle Spread
      const hand1Wrist = hands[0][0];
      const hand2Wrist = hands[1][0];

      const dist = Math.hypot(hand1Wrist.x - hand2Wrist.x, hand1Wrist.y - hand2Wrist.y);
      const targetScale = Math.min(2.4, Math.max(0.45, dist * 2.9));
      const targetSpread = Math.min(2.2, Math.max(0.5, dist * 2.6));

      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(targetScale, undefined, undefined, targetSpread);
      }

      detectedRaw = dist > 0.45 ? 'Two Fists (Expand Orb)' : 'Two Fists (Contract Orb)';

    } else if (hands.length === 1) {
      const lm = hands[0];

      const isOpenPalm = this.checkOpenPalm(lm);
      const isFist = this.checkClosedFist(lm);
      const isPinch = this.checkPinch(lm);

      // Smooth Wrist Rotation Mapping
      const wrist = lm[0];
      const middleKnuckle = lm[9];
      const rotY = (wrist.x - 0.5) * Math.PI * 2.2;
      const rotX = (wrist.y - 0.5) * Math.PI * 1.5;

      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(undefined, rotX, rotY, undefined);
      }

      // Swipe Gesture Motion Vector Tracking
      this.wristXBuffer.push(wrist.x);
      if (this.wristXBuffer.length > 5) this.wristXBuffer.shift();

      if (now > this.swipeCooldown && this.wristXBuffer.length >= 5) {
        const deltaX = this.wristXBuffer[this.wristXBuffer.length - 1] - this.wristXBuffer[0];
        if (deltaX < -0.16) {
          detectedRaw = 'Swipe Right (Next)';
          this.sendGestureCommand('next');
          this.swipeCooldown = now + 750;
        } else if (deltaX > 0.16) {
          detectedRaw = 'Swipe Left (Dismiss)';
          this.sendGestureCommand('dismiss');
          this.swipeCooldown = now + 750;
        }
      }

      if (detectedRaw === 'None') {
        if (isOpenPalm) {
          detectedRaw = 'Open Palm (Listen)';
        } else if (isFist) {
          detectedRaw = 'Closed Fist (Idle)';
        } else if (isPinch.active) {
          detectedRaw = `Pinch (Volume ${isPinch.volume}%)`;
          this.sendGestureCommand('volume', { level: isPinch.volume });
        }
      }
    }

    // Apply 3-frame stability debouncing for clean discrete triggers
    if (detectedRaw === this.pendingGesture) {
      this.pendingFrames++;
      if (this.pendingFrames >= this.REQUIRED_STABLE_FRAMES) {
        if (this.activeGesture !== detectedRaw) {
          this.activeGesture = detectedRaw;
          this.onGestureConfirmed(this.activeGesture);
        }
      }
    } else {
      this.pendingGesture = detectedRaw;
      this.pendingFrames = 1;
    }

    this.updateUI();
  }

  onGestureConfirmed(gestureName) {
    if (gestureName === 'Open Palm (Listen)') {
      if (jarvisOrb && jarvisOrb.state !== 'listening') {
        jarvisOrb.setState('listening');
        this.sendGestureCommand('activate');
      }
    } else if (gestureName === 'Closed Fist (Idle)') {
      if (jarvisOrb && jarvisOrb.state !== 'idle') {
        jarvisOrb.setState('idle');
        this.sendGestureCommand('idle');
      }
    }
  }

  checkOpenPalm(lm) {
    return (
      lm[8].y < lm[6].y &&  // Index
      lm[12].y < lm[10].y && // Middle
      lm[16].y < lm[14].y && // Ring
      lm[20].y < lm[18].y    // Pinky
    );
  }

  checkClosedFist(lm) {
    return (
      lm[8].y > lm[6].y &&
      lm[12].y > lm[10].y &&
      lm[16].y > lm[14].y &&
      lm[20].y > lm[18].y
    );
  }

  checkPinch(lm) {
    const dist = Math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y);
    const isPinch = dist < 0.06;
    const volPct = Math.round(Math.min(100, Math.max(0, (0.18 - dist) * 800)));
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
    ctx.lineWidth = 1.8;

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

    for (let i = 0; i < lm.length; i++) {
      ctx.beginPath();
      ctx.arc((1 - lm[i].x) * w, lm[i].y * h, 3.2, 0, 2 * Math.PI);
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
