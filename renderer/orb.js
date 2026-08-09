/**
 * Iron Man Jarvis 3D Glowing Particle Energy Sphere / Orb Renderer
 * Ultra-Smooth Delta-Time Lerp + Custom Shaders + UnrealBloomPass Post-Processing
 */

class JarvisOrb {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.width = window.innerWidth;
    this.height = window.innerHeight;

    // Current visual properties & targets for smooth lerping
    this.scale = 1.0;
    this.targetScale = 1.0;
    this.rotationX = 0;
    this.rotationY = 0;
    this.targetRotationX = 0;
    this.targetRotationY = 0;
    this.particleSpread = 1.0;
    this.targetParticleSpread = 1.0;
    this.brightness = 1.0;
    this.targetBrightness = 1.0;

    this.state = 'idle'; // 'idle', 'listening', 'thinking', 'speaking'
    this.lastTime = performance.now();

    this.initThree();
    this.createCoreSphere();
    this.createMagneticEnergyLines();
    this.createHUDRings();
    this.initPostProcessing();
    this.animate();

    window.addEventListener('resize', () => this.onWindowResize());
  }

  initThree() {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(60, this.width / this.height, 0.1, 1000);
    this.camera.position.z = 18;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 1.0);
    this.container.appendChild(this.renderer.domElement);
  }

  createCoreSphere() {
    const particleCount = 14000;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);
    const originalPositions = new Float32Array(particleCount * 3);

    const colorCore = new THREE.Color(0xffffff); // White-hot core
    const colorInner = new THREE.Color(0xffb400); // Warm gold
    const colorOuter = new THREE.Color(0xff5500); // Radiating orange
    const colorCyan = new THREE.Color(0x00f3ff); // Tech cyan accent

    for (let i = 0; i < particleCount; i++) {
      // Golden Ratio / Fibonacci sphere distribution
      const u = Math.random();
      const v = Math.random();
      const theta = u * 2.0 * Math.PI;
      const phi = Math.acos(2.0 * v - 1.0);

      const r = Math.pow(Math.random(), 0.65) * 4.5;
      const x = r * Math.sin(phi) * Math.cos(theta);
      const y = r * Math.sin(phi) * Math.sin(theta);
      const z = r * Math.cos(phi);

      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;

      originalPositions[i * 3] = x;
      originalPositions[i * 3 + 1] = y;
      originalPositions[i * 3 + 2] = z;

      const normalizedDist = r / 4.5;
      let particleColor;
      if (normalizedDist < 0.2) {
        particleColor = colorCore;
      } else if (normalizedDist < 0.6) {
        particleColor = colorInner;
      } else if (Math.random() < 0.2) {
        particleColor = colorCyan;
      } else {
        particleColor = colorOuter;
      }

      colors[i * 3] = particleColor.r;
      colors[i * 3 + 1] = particleColor.g;
      colors[i * 3 + 2] = particleColor.b;

      sizes[i] = (1.0 - normalizedDist * 0.4) * (Math.random() * 2.8 + 1.2);
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    this.originalPositions = originalPositions;

    // Shader Material with Delta-Time Harmonic Turbulence
    const vertexShader = `
      attribute float size;
      attribute vec3 color;
      varying vec3 vColor;
      uniform float uTime;
      uniform float uSpread;

      void main() {
        vColor = color;
        vec3 pos = position * uSpread;

        // Smooth multi-harmonic organic turbulence
        pos.x += sin(uTime * 2.5 + position.y * 1.8) * 0.09;
        pos.y += cos(uTime * 2.5 + position.z * 1.8) * 0.09;
        pos.z += sin(uTime * 2.5 + position.x * 1.8) * 0.09;

        vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
        gl_PointSize = size * (260.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `;

    const fragmentShader = `
      varying vec3 vColor;
      uniform float uBrightness;

      void main() {
        float dist = length(gl_PointCoord - vec2(0.5));
        if (dist > 0.5) discard;

        float alpha = clamp((0.5 - dist) * 2.0, 0.0, 1.0);
        alpha = pow(alpha, 1.4);

        gl_FragColor = vec4(vColor * uBrightness, alpha);
      }
    `;

    this.orbUniforms = {
      uTime: { value: 0 },
      uSpread: { value: 1.0 },
      uBrightness: { value: 1.0 },
    };

    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: this.orbUniforms,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      transparent: true,
    });

    this.particleSphere = new THREE.Points(geometry, material);
    this.scene.add(this.particleSphere);
  }

  createMagneticEnergyLines() {
    const lineCount = 400;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(lineCount * 2 * 3);

    for (let i = 0; i < lineCount; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.random() * Math.PI;

      const r1 = 0.4;
      const x1 = r1 * Math.sin(phi) * Math.cos(theta);
      const y1 = r1 * Math.sin(phi) * Math.sin(theta);
      const z1 = r1 * Math.cos(phi);

      const r2 = 4.8 + Math.random() * 1.6;
      const x2 = r2 * Math.sin(phi) * Math.cos(theta);
      const y2 = r2 * Math.sin(phi) * Math.sin(theta);
      const z2 = r2 * Math.cos(phi);

      positions[i * 6] = x1;
      positions[i * 6 + 1] = y1;
      positions[i * 6 + 2] = z1;

      positions[i * 6 + 3] = x2;
      positions[i * 6 + 4] = y2;
      positions[i * 6 + 5] = z2;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.LineBasicMaterial({
      color: 0xff8800,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
    });

    this.energyLines = new THREE.LineSegments(geometry, material);
    this.scene.add(this.energyLines);
  }

  createHUDRings() {
    this.hudGroup = new THREE.Group();

    const ringMat1 = new THREE.MeshBasicMaterial({
      color: 0x00f3ff,
      wireframe: true,
      transparent: true,
      opacity: 0.4,
      blending: THREE.AdditiveBlending,
    });
    const ringMat2 = new THREE.MeshBasicMaterial({
      color: 0xffa500,
      wireframe: true,
      transparent: true,
      opacity: 0.3,
      blending: THREE.AdditiveBlending,
    });

    const ring1 = new THREE.Mesh(new THREE.TorusGeometry(5.8, 0.04, 16, 100), ringMat1);
    ring1.rotation.x = Math.PI / 3;

    const ring2 = new THREE.Mesh(new THREE.TorusGeometry(6.4, 0.03, 16, 100), ringMat2);
    ring2.rotation.y = Math.PI / 4;

    const ring3 = new THREE.Mesh(new THREE.TorusGeometry(7.2, 0.02, 16, 100), ringMat1);
    ring3.rotation.x = -Math.PI / 4;

    this.hudGroup.add(ring1);
    this.hudGroup.add(ring2);
    this.hudGroup.add(ring3);
    this.hudRings = [ring1, ring2, ring3];

    this.scene.add(this.hudGroup);
  }

  initPostProcessing() {
    this.composer = new THREE.EffectComposer(this.renderer);
    const renderPass = new THREE.RenderPass(this.scene, this.camera);
    this.composer.addPass(renderPass);

    const bloomPass = new THREE.UnrealBloomPass(
      new THREE.Vector2(this.width, this.height),
      1.8,
      0.4,
      0.15
    );
    this.composer.addPass(bloomPass);
    this.bloomPass = bloomPass;
  }

  setState(stateName) {
    this.state = stateName;
    const statusBadge = document.getElementById('hud-status');

    if (statusBadge) {
      statusBadge.className = 'hud-status-badge ' + stateName;
      statusBadge.textContent = stateName.toUpperCase() + ' • ONLINE';
    }

    if (stateName === 'listening') {
      this.targetBrightness = 1.6;
      this.targetParticleSpread = 1.25;
      this.bloomPass.strength = 2.4;
    } else if (stateName === 'thinking') {
      this.targetBrightness = 2.0;
      this.targetParticleSpread = 1.4;
      this.bloomPass.strength = 3.0;
    } else if (stateName === 'speaking') {
      this.targetBrightness = 1.8;
      this.targetParticleSpread = 1.15;
      this.bloomPass.strength = 2.2;
    } else {
      // idle
      this.targetBrightness = 1.0;
      this.targetParticleSpread = 1.0;
      this.bloomPass.strength = 1.8;
    }
  }

  setGestureInputs(scaleFactor, rotX, rotY, particleSpread) {
    if (scaleFactor !== undefined) this.targetScale = scaleFactor;
    if (rotX !== undefined) this.targetRotationX = rotX;
    if (rotY !== undefined) this.targetRotationY = rotY;
    if (particleSpread !== undefined) this.targetParticleSpread = particleSpread;
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    const now = performance.now();
    const dt = Math.min(0.1, (now - this.lastTime) * 0.001);
    this.lastTime = now;
    const time = now * 0.001;

    // Delta-Time Exponential Lerp for 100% Frame-Rate Independent Smoothness
    const lerpSpeed = 10.0; // Responsive spring speed
    const lerpFactor = 1.0 - Math.exp(-lerpSpeed * dt);

    this.scale += (this.targetScale - this.scale) * lerpFactor;
    this.rotationX += (this.targetRotationX - this.rotationX) * lerpFactor;
    this.rotationY += (this.targetRotationY - this.rotationY) * lerpFactor;
    this.particleSpread += (this.targetParticleSpread - this.particleSpread) * lerpFactor;
    this.brightness += (this.targetBrightness - this.brightness) * lerpFactor;

    // Apply scale & rotation
    this.particleSphere.scale.set(this.scale, this.scale, this.scale);
    this.energyLines.scale.set(this.scale, this.scale, this.scale);
    this.hudGroup.scale.set(this.scale, this.scale, this.scale);

    this.particleSphere.rotation.x = this.rotationX + Math.sin(time * 0.5) * 0.08;
    this.particleSphere.rotation.y = this.rotationY + time * 0.25;
    this.energyLines.rotation.y = -time * 0.35;

    // Smooth HUD ring rotations
    if (this.hudRings) {
      this.hudRings[0].rotation.z = time * 0.5;
      this.hudRings[1].rotation.z = -time * 0.4;
      this.hudRings[2].rotation.z = time * 0.35;
    }

    // Audio-reactive state modulations
    if (this.state === 'speaking') {
      const pulse = 1.0 + Math.sin(time * 14.0) * 0.07;
      this.particleSphere.scale.multiplyScalar(pulse);
    } else if (this.state === 'thinking') {
      this.particleSphere.rotation.y += 0.04;
    }

    // Update Shader Uniforms
    this.orbUniforms.uTime.value = time;
    this.orbUniforms.uSpread.value = this.particleSpread;
    this.orbUniforms.uBrightness.value = this.brightness;

    // Render Scene through UnrealBloomPass
    this.composer.render();
  }

  onWindowResize() {
    this.width = window.innerWidth;
    this.height = window.innerHeight;

    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();

    this.renderer.setSize(this.width, this.height);
    this.composer.setSize(this.width, this.height);
  }
}

let jarvisOrb = null;
document.addEventListener('DOMContentLoaded', () => {
  jarvisOrb = new JarvisOrb('webgl-container');
});
