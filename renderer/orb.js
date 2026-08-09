/**
 * Iron Man Jarvis 3D Glowing Particle Energy Sphere / Orb Renderer
 * Built with Three.js + Custom Shaders + UnrealBloomPass Post-Processing
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
    const particleCount = 12000;
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
      // Sphere distribution using Fibonacci sphere algorithm
      const u = Math.random();
      const v = Math.random();
      const theta = u * 2.0 * Math.PI;
      const phi = Math.acos(2.0 * v - 1.0);

      const r = Math.pow(Math.random(), 0.7) * 4.5; // Radius up to 4.5
      const x = r * Math.sin(phi) * Math.cos(theta);
      const y = r * Math.sin(phi) * Math.sin(theta);
      const z = r * Math.cos(phi);

      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;

      originalPositions[i * 3] = x;
      originalPositions[i * 3 + 1] = y;
      originalPositions[i * 3 + 2] = z;

      // Color gradient from core to outer edge
      const normalizedDist = r / 4.5;
      let particleColor;
      if (normalizedDist < 0.25) {
        particleColor = colorCore;
      } else if (normalizedDist < 0.65) {
        particleColor = colorInner;
      } else if (Math.random() < 0.15) {
        particleColor = colorCyan;
      } else {
        particleColor = colorOuter;
      }

      colors[i * 3] = particleColor.r;
      colors[i * 3 + 1] = particleColor.g;
      colors[i * 3 + 2] = particleColor.b;

      sizes[i] = (1.0 - normalizedDist * 0.5) * (Math.random() * 2.5 + 1.2);
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    this.originalPositions = originalPositions;

    // Custom Shader Material for glowing particles
    const vertexShader = `
      attribute float size;
      attribute vec3 color;
      varying vec3 vColor;
      uniform float uTime;
      uniform float uSpread;

      void main() {
        vColor = color;
        vec3 pos = position * uSpread;

        // Subtle high-frequency turbulence jitter
        pos.x += sin(uTime * 3.0 + position.y * 2.0) * 0.08;
        pos.y += cos(uTime * 3.0 + position.z * 2.0) * 0.08;
        pos.z += sin(uTime * 3.0 + position.x * 2.0) * 0.08;

        vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
        gl_PointSize = size * (250.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `;

    const fragmentShader = `
      varying vec3 vColor;
      uniform float uBrightness;

      void main() {
        // Soft circular glow point
        float dist = length(gl_PointCoord - vec2(0.5));
        if (dist > 0.5) discard;

        float alpha = clamp((0.5 - dist) * 2.0, 0.0, 1.0);
        alpha = pow(alpha, 1.5);

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
    const lineCount = 350;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(lineCount * 2 * 3);

    for (let i = 0; i < lineCount; i++) {
      // Arcing field lines connecting inner core outward
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.random() * Math.PI;

      const r1 = 0.5;
      const x1 = r1 * Math.sin(phi) * Math.cos(theta);
      const y1 = r1 * Math.sin(phi) * Math.sin(theta);
      const z1 = r1 * Math.cos(phi);

      const r2 = 4.8 + Math.random() * 1.5;
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

    // Orbiting Circular Scan Line Rings
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

    // UnrealBloomPass for Iron Man HDR Glow
    const bloomPass = new THREE.UnrealBloomPass(
      new THREE.Vector2(this.width, this.height),
      1.8, // Bloom strength
      0.4, // Radius
      0.15 // Threshold
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
    if (scaleFactor) this.targetScale = scaleFactor;
    if (rotX !== undefined) this.targetRotationX = rotX;
    if (rotY !== undefined) this.targetRotationY = rotY;
    if (particleSpread) this.targetParticleSpread = particleSpread;
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    const time = performance.now() * 0.001;

    // Smooth Lerp target visual states (dt lerp factor ~0.15)
    this.scale += (this.targetScale - this.scale) * 0.15;
    this.rotationX += (this.targetRotationX - this.rotationX) * 0.15;
    this.rotationY += (this.targetRotationY - this.rotationY) * 0.15;
    this.particleSpread += (this.targetParticleSpread - this.particleSpread) * 0.15;
    this.brightness += (this.targetBrightness - this.brightness) * 0.15;

    // Apply scale & rotation to particle sphere & energy lines
    this.particleSphere.scale.set(this.scale, this.scale, this.scale);
    this.energyLines.scale.set(this.scale, this.scale, this.scale);
    this.hudGroup.scale.set(this.scale, this.scale, this.scale);

    // Ambient rotation + gesture wrist rotation
    this.particleSphere.rotation.x = this.rotationX + Math.sin(time * 0.5) * 0.1;
    this.particleSphere.rotation.y = this.rotationY + time * 0.3;
    this.energyLines.rotation.y = -time * 0.4;

    // Rotate HUD Rings
    if (this.hudRings) {
      this.hudRings[0].rotation.z = time * 0.6;
      this.hudRings[1].rotation.z = -time * 0.5;
      this.hudRings[2].rotation.z = time * 0.4;
    }

    // Dynamic state modulations
    if (this.state === 'speaking') {
      const pulse = 1.0 + Math.sin(time * 12.0) * 0.08;
      this.particleSphere.scale.multiplyScalar(pulse);
    } else if (this.state === 'thinking') {
      this.particleSphere.rotation.y += 0.05;
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

// Instantiate global Orb renderer on page load
let jarvisOrb = null;
document.addEventListener('DOMContentLoaded', () => {
  jarvisOrb = new JarvisOrb('webgl-container');
});
