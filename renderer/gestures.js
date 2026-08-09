/**
 * MediaPipe Hands Ultra-Smooth Real-Time Gesture Recognition & Filter Layer
 * Native HTML5 getUserMedia Loop + Orientation-Invariant Distance Ratios + UI Chip Sync
 */

class GestureController {
  constructor() {
    this.videoElement = document.getElementById('webcam-video');
    this.canvasElement = document.getElementById('landmark-canvas');
    this.canvasCtx = this.canvasElement ? this.canvasElement.getContext('2d') : null;

    // Smoothed landmarks & historical velocity tracking
    this.smoothedLandmarks = [];
    this.prevRawLandmarks = [];

    // Multi-frame state debouncing
    this.activeGesture = 'None';
    this.pendingGesture = 'None';
    this.pendingFrames = 0;
    this.REQUIRED_STABLE_FRAMES = 2; // 2-3 frames (~60ms) fast stable switch

    // Swipe tracking buffer
    this.wristXBuffer = [];
    this.swipeCooldown = 0;

    this.showOverlay = true;

    this.initMediaPipe();
  }

  initMediaPipe() {
    if (typeof Hands === 'undefined') {
      console.warn('[Gestures] MediaPipe Hands CDN loading...');
      setTimeout(() => this.initMediaPipe(), 500);
      return;
    }

    try {
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
      this.startDirectWebcam();
    } catch (err) {
      console.error('❌ [Gestures] MediaPipe initialization error:', err);
    }
  }

  async startDirectWebcam(attempt = 1) {
    console.log(`🎥 [Gestures] Initializing WebCam tracking (Attempt ${attempt}/8)...`);
    const gestureEl = document.getElementById('gesture-name');
    if (gestureEl && this.activeGesture === 'None') {
      gestureEl.textContent = `Camera Init (${attempt})...`;
    }

    if (attempt === 1) {
      await new Promise(r => setTimeout(r, 400));
    }

    try {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } }
        });
      } catch (e1) {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
      }

      this.videoElement.srcObject = stream;
      await this.videoElement.play();

      console.log('✅ [Gestures] WebCam stream connected & tracking active!');
      if (gestureEl && (gestureEl.textContent.includes('Camera Init') || gestureEl.textContent === 'None')) {
        gestureEl.textContent = 'Tracking Active';
      }

      let isProcessing = false;
      const processFrame = async () => {
        if (this.hands && this.videoElement.readyState >= 2 && !isProcessing) {
          isProcessing = true;
          try {
            await this.hands.send({ image: this.videoElement });
          } catch (e) {
            console.error('[Gestures] Frame send error:', e);
          }
          isProcessing = false;
        }
        requestAnimationFrame(processFrame);
      };
      requestAnimationFrame(processFrame);

    } catch (err) {
      console.warn(`⚠️ [Gestures] WebCam access busy on attempt ${attempt}: ${err.message}. Retrying in 600ms...`);
      if (attempt < 8) {
        setTimeout(() => this.startDirectWebcam(attempt + 1), 600);
      } else {
        console.error('❌ [Gestures] Failed to acquire WebCam after 8 attempts.');
        if (gestureEl) gestureEl.textContent = 'Camera Busy / Failed';
      }
    }
  }

  onResults(results) {
    if (this.canvasCtx) {
      this.canvasCtx.save();
      this.canvasCtx.clearRect(0, 0, this.canvasElement.width, this.canvasElement.height);
    }

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
      if (this.canvasCtx) this.canvasCtx.restore();
      return;
    }

    const rawHands = results.multiHandLandmarks;
    this.adaptiveSmoothLandmarks(rawHands);

    if (this.showOverlay && this.canvasCtx) {
      for (const landmarks of this.smoothedLandmarks) {
        this.drawHandOverlay(landmarks);
      }
    }

    this.processGestures(this.smoothedLandmarks);

    if (this.canvasCtx) this.canvasCtx.restore();
  }

  /**
   * Adaptive Velocity Low-Pass Filter
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
        const dx = rawPoints[i].x - prevPoints[i].x;
        const dy = rawPoints[i].y - prevPoints[i].y;
        const vel = Math.hypot(dx, dy);

        const alpha = Math.min(0.5, Math.max(0.15, vel * 7.0));

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
    let chipKey = 'none';

    if (hands.length === 2) {
      // TWO HAND GESTURES: Dynamic Scale & Particle Spread
      const hand1Wrist = hands[0][0];
      const hand2Wrist = hands[1][0];

      const dist = Math.hypot(hand1Wrist.x - hand2Wrist.x, hand1Wrist.y - hand2Wrist.y);
      const targetScale = Math.min(2.5, Math.max(0.4, dist * 3.0));
      const targetSpread = Math.min(2.3, Math.max(0.5, dist * 2.7));

      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(targetScale, undefined, undefined, targetSpread);
      }

      detectedRaw = dist > 0.45 ? 'Two Fists (Expand Orb)' : 'Two Fists (Contract Orb)';
      chipKey = 'two_fists';

    } else if (hands.length === 1) {
      const lm = hands[0];

      const isOpenPalm = this.checkOpenPalm(lm);
      const isFist = this.checkClosedFist(lm);
      const isPinch = this.checkPinch(lm);

      // Smooth Wrist Rotation Mapping
      const wrist = lm[0];
      const rotY = (wrist.x - 0.5) * Math.PI * 2.4;
      const rotX = (wrist.y - 0.5) * Math.PI * 1.6;

      if (jarvisOrb) {
        jarvisOrb.setGestureInputs(undefined, rotX, rotY, undefined);
      }

      // Swipe Gesture Motion Vector Tracking
      this.wristXBuffer.push(wrist.x);
      if (this.wristXBuffer.length > 5) this.wristXBuffer.shift();

      if (now > this.swipeCooldown && this.wristXBuffer.length >= 5) {
        const deltaX = this.wristXBuffer[this.wristXBuffer.length - 1] - this.wristXBuffer[0];
        if (deltaX < -0.14) {
          detectedRaw = 'Swipe Right (Next)';
          chipKey = 'swipe';
          this.sendGestureCommand('next');
          this.swipeCooldown = now + 750;
        } else if (deltaX > 0.14) {
          detectedRaw = 'Swipe Left (Dismiss)';
          chipKey = 'swipe';
          this.sendGestureCommand('dismiss');
          this.swipeCooldown = now + 750;
        }
      }

      if (detectedRaw === 'None') {
        if (isOpenPalm) {
          detectedRaw = 'Open Palm (Listen)';
          chipKey = 'open_palm';
        } else if (isFist) {
          detectedRaw = 'Closed Fist (Idle)';
          chipKey = 'fist';
        } else if (isPinch.active) {
          detectedRaw = `Pinch (Volume ${isPinch.volume}%)`;
          this.sendGestureCommand('volume', { level: isPinch.volume });
        } else {
          chipKey = 'rotate';
        }
      }
    }

    // Apply stability debouncing for clean discrete triggers
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

    this.activeChipKey = chipKey;
    this.updateUI();
  }

  onGestureConfirmed(gestureName) {
    console.log(`🖐️ [Gesture Confirmed] ${gestureName}`);
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

  /**
   * Orientation-Invariant Distance Ratio Calculation for 100% Reliable Hand Detection
   */
  checkOpenPalm(lm) {
    const wrist = lm[0];
    const fingerTips = [8, 12, 16, 20];
    const fingerKnuckles = [5, 9, 13, 17];

    let openFingers = 0;
    for (let i = 0; i < 4; i++) {
      const distTip = Math.hypot(lm[fingerTips[i]].x - wrist.x, lm[fingerTips[i]].y - wrist.y);
      const distKnuckle = Math.hypot(lm[fingerKnuckles[i]].x - wrist.x, lm[fingerKnuckles[i]].y - wrist.y);
      if (distTip > distKnuckle * 1.25) {
        openFingers++;
      }
    }
    return openFingers >= 3;
  }

  checkClosedFist(lm) {
    const wrist = lm[0];
    const fingerTips = [8, 12, 16, 20];
    const fingerKnuckles = [5, 9, 13, 17];

    let curledFingers = 0;
    for (let i = 0; i < 4; i++) {
      const distTip = Math.hypot(lm[fingerTips[i]].x - wrist.x, lm[fingerTips[i]].y - wrist.y);
      const distKnuckle = Math.hypot(lm[fingerKnuckles[i]].x - wrist.x, lm[fingerKnuckles[i]].y - wrist.y);
      if (distTip < distKnuckle * 1.1) {
        curledFingers++;
      }
    }
    return curledFingers >= 3;
  }

  checkPinch(lm) {
    const dist = Math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y);
    const isPinch = dist < 0.065;
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
    if (!this.canvasCtx) return;
    const ctx = this.canvasCtx;
    const w = this.canvasElement.width;
    const h = this.canvasElement.height;

    ctx.strokeStyle = '#00e8ff';
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
      ctx.arc((1 - lm[i].x) * w, lm[i].y * h, 3.0, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  updateUI() {
    const gestureEl = document.getElementById('gesture-name');
    const scaleEl = document.getElementById('orb-scale-val');

    if (gestureEl) gestureEl.textContent = this.activeGesture;
    if (scaleEl && jarvisOrb) scaleEl.textContent = jarvisOrb.scale.toFixed(2);

    // Sync HUD Gesture Chips highlighting
    const chips = document.querySelectorAll('.gesture-chip');
    chips.forEach(chip => {
      const key = chip.getAttribute('data-gesture');
      if (key === this.activeChipKey) {
        chip.classList.add('active');
      } else {
        chip.classList.remove('active');
      }
    });
  }
}

function toggleDebugOverlay() {
  const feed = document.querySelector('.tracking-feed');
  if (feed) feed.classList.toggle('hidden');
}

let gestureController = null;
document.addEventListener('DOMContentLoaded', () => {
  gestureController = new GestureController();
});
