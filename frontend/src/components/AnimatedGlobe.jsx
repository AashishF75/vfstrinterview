import React, { useRef, useEffect, useState } from 'react';

/**
 * AnimatedGlobe Component
 *
 * A high-performance, luminous Canvas 2D particle globe with 3D projection.
 * Features:
 * - Dominant luminous white particles with subtle cyan and violet accents
 * - Pronounced 3D depth, front-facing particle glow, and depth-of-field attenuation
 * - Wide atmospheric diffuse halo and bright horizon rim
 * - Thin, elegant orbital trajectory rings with orbiting glowing beacons
 * - Geodesic connection arcs with traveling pulses
 * - Interactive mouse tilt reaction
 * - Automatic HiDPI scaling, resize observation, hidden-tab pausing,
 *   and prefers-reduced-motion compliance.
 */
export default function AnimatedGlobe({
  className = '',
  size = 640,
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const animationFrameRef = useRef(null);
  const mouseRef = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });

  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handleChange = (e) => setPrefersReducedMotion(e.matches);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let isDestroyed = false;
    let isHidden = false;

    // Detect mobile for particle scaling and performance
    const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
    const particleCount = isMobile ? 650 : 1350;

    // Generate Fibonacci Sphere Particles
    const phi = Math.PI * (3 - Math.sqrt(5)); // Golden angle ~2.3999632
    const sphereParticles = [];

    for (let i = 0; i < particleCount; i++) {
      const y = 1 - (i / (particleCount - 1)) * 2; // 1 to -1
      const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = phi * i;
      const x = Math.cos(theta) * radiusAtY;
      const z = Math.sin(theta) * radiusAtY;

      // Color tier: 75% pure luminous white, 18% bright cyan, 7% electric violet
      const rand = Math.random();
      let colorType = 'white';
      if (rand > 0.75 && rand <= 0.93) colorType = 'cyan';
      else if (rand > 0.93) colorType = 'violet';

      sphereParticles.push({
        x,
        y,
        z,
        baseSize: 0.9 + Math.random() * 1.5,
        twinkleOffset: Math.random() * Math.PI * 2,
        twinkleSpeed: 0.6 + Math.random() * 1.4,
        colorType,
      });
    }

    // Geodesic Data Arcs (network connections between surface node pairs)
    const arcCount = isMobile ? 5 : 10;
    const arcs = [];
    for (let i = 0; i < arcCount; i++) {
      const idxA = Math.floor(Math.random() * particleCount);
      let idxB = Math.floor(Math.random() * particleCount);
      while (idxB === idxA) idxB = Math.floor(Math.random() * particleCount);
      arcs.push({
        nodeA: sphereParticles[idxA],
        nodeB: sphereParticles[idxB],
        pulseProgress: Math.random(),
        pulseSpeed: 0.003 + Math.random() * 0.005,
      });
    }

    // Thin, Elegant Orbital Rings (tilted 3D coordinate planes)
    const rings = [
      {
        radiusRatio: 1.24,
        tiltX: 0.44, // ~25 deg
        tiltZ: 0.30,
        speed: 0.007,
        dash: [4, 6],
        strokeColor: 'rgba(56, 189, 248, 0.40)',
        satellites: [
          { angle: 0, size: 3.4, color: '#ffffff', glowColor: 'rgba(56, 189, 248, 0.5)' },
          { angle: Math.PI * 1.05, size: 2.6, color: '#c084fc', glowColor: 'rgba(192, 132, 252, 0.45)' },
        ],
      },
      {
        radiusRatio: 1.38,
        tiltX: -0.46, // ~-26 deg
        tiltZ: -0.32,
        speed: -0.005,
        dash: [3, 8],
        strokeColor: 'rgba(168, 85, 247, 0.32)',
        satellites: [
          { angle: Math.PI * 0.45, size: 3.0, color: '#38bdf8', glowColor: 'rgba(56, 189, 248, 0.5)' },
          { angle: Math.PI * 1.5, size: 2.4, color: '#ffffff', glowColor: 'rgba(255, 255, 255, 0.4)' },
        ],
      },
    ];

    // Animation & Rotation State
    let angleY = 0;
    const baseTiltX = -0.22; // ~-12.5 deg natural axial tilt
    let lastTime = performance.now();

    // Canvas Sizing with DPR
    let width = size;
    let height = size;

    const updateDimensions = () => {
      if (!canvas || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const currentWidth = Math.max(300, rect.width || size);
      const currentHeight = Math.max(300, rect.height || currentWidth);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);

      width = currentWidth;
      height = currentHeight;

      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
    };

    updateDimensions();

    const resizeObserver = new ResizeObserver(() => {
      updateDimensions();
    });
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    // Visibility Handler
    const handleVisibilityChange = () => {
      isHidden = document.hidden;
      if (!isHidden) {
        lastTime = performance.now();
        if (!animationFrameRef.current) {
          animationFrameRef.current = requestAnimationFrame(render);
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Mouse Movement for interactive 3D tilt
    const handleMouseMove = (e) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width - 0.5;
      const ny = (e.clientY - rect.top) / rect.height - 0.5;
      mouseRef.current.targetX = nx * 0.32;
      mouseRef.current.targetY = ny * 0.32;
    };

    const handleMouseLeave = () => {
      mouseRef.current.targetX = 0;
      mouseRef.current.targetY = 0;
    };

    const containerEl = containerRef.current;
    if (containerEl) {
      containerEl.addEventListener('mousemove', handleMouseMove);
      containerEl.addEventListener('mouseleave', handleMouseLeave);
    }

    // Main 3D Render Loop
    const render = (now) => {
      if (isDestroyed) return;
      if (isHidden) {
        animationFrameRef.current = null;
        return;
      }

      const delta = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      // Continuous rotation
      if (!prefersReducedMotion) {
        angleY += delta * 0.24; // Smooth, continuous rotation
      }

      // Smooth mouse lerp
      mouseRef.current.x += (mouseRef.current.targetX - mouseRef.current.x) * 0.05;
      mouseRef.current.y += (mouseRef.current.targetY - mouseRef.current.y) * 0.05;

      const currentTiltX = baseTiltX + mouseRef.current.y;
      const currentAngleY = angleY + mouseRef.current.x;

      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      // Generous globe radius: occupies ~76% of canvas width/height
      const globeRadius = Math.min(width, height) * 0.38;
      const fov = globeRadius * 3.4;

      // 1. Soft, Diffuse Halo & Atmospheric Inner Glow
      const ambientGrad = ctx.createRadialGradient(
        cx,
        cy,
        globeRadius * 0.15,
        cx,
        cy,
        globeRadius * 1.52
      );
      ambientGrad.addColorStop(0, 'rgba(255, 255, 255, 0.09)');
      ambientGrad.addColorStop(0.25, 'rgba(56, 189, 248, 0.24)');
      ambientGrad.addColorStop(0.55, 'rgba(99, 102, 241, 0.14)');
      ambientGrad.addColorStop(0.82, 'rgba(168, 85, 247, 0.06)');
      ambientGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');

      ctx.fillStyle = ambientGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, globeRadius * 1.55, 0, Math.PI * 2);
      ctx.fill();

      // Bright, Luminous Horizon Rim
      ctx.save();
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.38)';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.arc(cx, cy, globeRadius, 0, Math.PI * 2);
      ctx.stroke();

      // Subtle upper-horizon Fresnel highlight
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.50)';
      ctx.lineWidth = 1.0;
      ctx.beginPath();
      ctx.arc(cx, cy, globeRadius + 1.2, -Math.PI * 0.8, -Math.PI * 0.1);
      ctx.stroke();
      ctx.restore();

      // 2. Rotate and Project Particles
      const cosY = Math.cos(currentAngleY);
      const sinY = Math.sin(currentAngleY);
      const cosX = Math.cos(currentTiltX);
      const sinX = Math.sin(currentTiltX);

      const projected = [];

      for (let i = 0; i < sphereParticles.length; i++) {
        const p = sphereParticles[i];

        // Rotate Y
        const x1 = p.x * cosY - p.z * sinY;
        const z1 = p.x * sinY + p.z * cosY;

        // Rotate X
        const y2 = p.y * cosX - z1 * sinX;
        const z2 = p.y * sinX + z1 * cosX;
        const x2 = x1;

        // Perspective Projection
        const scale = fov / (fov + z2 * globeRadius);
        const px = cx + x2 * globeRadius * scale;
        const py = cy + y2 * globeRadius * scale;

        // Depth and twinkle
        const twinkle = prefersReducedMotion
          ? 1
          : 0.85 + 0.25 * Math.sin(now * 0.002 * p.twinkleSpeed + p.twinkleOffset);

        projected.push({
          px,
          py,
          z: z2, // -1 (back) to +1 (front)
          scale,
          colorType: p.colorType,
          baseSize: p.baseSize,
          twinkle,
        });
      }

      // Sort by depth (back to front) for accurate 3D occlusion
      projected.sort((a, b) => a.z - b.z);

      // 3. Render Particles with Rich Brightness & Depth
      for (let i = 0; i < projected.length; i++) {
        const pt = projected[i];
        const isFront = pt.z >= 0;

        // Normalized depth from 0 (back) to 1 (front)
        const depthFactor = (pt.z + 1) / 2;

        let alpha;
        let radius;

        if (isFront) {
          // Front particles: prominent, crisp, and luminous
          alpha = Math.min(1.0, (0.55 + depthFactor * 0.45) * pt.twinkle);
          radius = pt.baseSize * pt.scale * (1.0 + depthFactor * 0.7);
        } else {
          // Rear particles: softened to convey genuine spherical depth
          alpha = Math.max(0.06, (0.08 + depthFactor * 0.35) * pt.twinkle);
          radius = pt.baseSize * pt.scale * 0.75;
          if (radius < 0.5) radius = 0.5;
        }

        // Draw particle body
        ctx.beginPath();
        ctx.arc(pt.px, pt.py, radius, 0, Math.PI * 2);

        if (pt.colorType === 'white') {
          ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        } else if (pt.colorType === 'cyan') {
          ctx.fillStyle = `rgba(125, 211, 252, ${alpha})`;
        } else {
          ctx.fillStyle = `rgba(216, 180, 254, ${alpha})`;
        }
        ctx.fill();

        // Extra outer glow for prominent front-facing particles
        if (isFront && pt.z > 0.35) {
          ctx.beginPath();
          ctx.arc(pt.px, pt.py, radius * 2.2, 0, Math.PI * 2);
          if (pt.colorType === 'white') {
            ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.35})`;
          } else {
            ctx.fillStyle = `rgba(56, 189, 248, ${alpha * 0.30})`;
          }
          ctx.fill();

          // Core highlights on nearest particles
          if (pt.z > 0.65) {
            ctx.beginPath();
            ctx.arc(pt.px, pt.py, radius * 3.4, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(56, 189, 248, ${alpha * 0.15})`;
            ctx.fill();
          }
        }
      }

      // 4. Render Geodesic Data Arcs
      ctx.save();
      for (let i = 0; i < arcs.length; i++) {
        const arc = arcs[i];
        if (!prefersReducedMotion) {
          arc.pulseProgress = (arc.pulseProgress + arc.pulseSpeed) % 1;
        }

        // Project Node A
        const aX1 = arc.nodeA.x * cosY - arc.nodeA.z * sinY;
        const aZ1 = arc.nodeA.x * sinY + arc.nodeA.z * cosY;
        const aY2 = arc.nodeA.y * cosX - aZ1 * sinX;
        const aZ2 = arc.nodeA.y * sinX + aZ1 * cosX;
        const scaleA = fov / (fov + aZ2 * globeRadius);
        const pAx = cx + aX1 * globeRadius * scaleA;
        const pAy = cy + aY2 * globeRadius * scaleA;

        // Project Node B
        const bX1 = arc.nodeB.x * cosY - arc.nodeB.z * sinY;
        const bZ1 = arc.nodeB.x * sinY + arc.nodeB.z * cosY;
        const bY2 = arc.nodeB.y * cosX - bZ1 * sinX;
        const bZ2 = arc.nodeB.y * sinX + bZ1 * cosX;
        const scaleB = fov / (fov + bZ2 * globeRadius);
        const pBx = cx + bX1 * globeRadius * scaleB;
        const pBy = cy + bY2 * globeRadius * scaleB;

        // Render when at least one node is on front hemisphere
        if (aZ2 > -0.15 || bZ2 > -0.15) {
          const arcAlpha = Math.max(0, Math.min(0.42, ((aZ2 + bZ2) / 2 + 0.35) * 0.45));
          ctx.strokeStyle = `rgba(186, 230, 253, ${arcAlpha})`;
          ctx.lineWidth = 1.0;
          ctx.beginPath();
          ctx.moveTo(pAx, pAy);

          const midX = (pAx + pBx) / 2;
          const midY = (pAy + pBy) / 2;
          const elevation = 14 * Math.max(scaleA, scaleB);
          ctx.quadraticCurveTo(midX, midY - elevation, pBx, pBy);
          ctx.stroke();

          // Traveling pulse particle along the arc
          const t = arc.pulseProgress;
          const pulseX = (1 - t) * (1 - t) * pAx + 2 * (1 - t) * t * midX + t * t * pBx;
          const pulseY = (1 - t) * (1 - t) * pAy + 2 * (1 - t) * t * (midY - elevation) + t * t * pBy;
          ctx.fillStyle = `rgba(255, 255, 255, ${arcAlpha * 2.4})`;
          ctx.beginPath();
          ctx.arc(pulseX, pulseY, 1.8, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.restore();

      // 5. Render Thin, Elegant Orbital Rings
      for (let rIdx = 0; rIdx < rings.length; rIdx++) {
        const ring = rings[rIdx];
        const ringRadius = globeRadius * ring.radiusRatio;

        ctx.save();
        ctx.translate(cx, cy);

        // Apply orbital ring orientation
        ctx.rotate(ring.tiltZ);
        ctx.scale(1, Math.cos(ring.tiltX));

        // Draw dotted orbital trajectory
        ctx.strokeStyle = ring.strokeColor;
        ctx.lineWidth = 1.1;
        ctx.setLineDash(ring.dash);
        ctx.beginPath();
        ctx.arc(0, 0, ringRadius, 0, Math.PI * 2);
        ctx.stroke();

        // Update and draw orbital satellite beacons
        for (let sIdx = 0; sIdx < ring.satellites.length; sIdx++) {
          const sat = ring.satellites[sIdx];
          if (!prefersReducedMotion) {
            sat.angle += ring.speed;
          }

          const satX = Math.cos(sat.angle) * ringRadius;
          const satY = Math.sin(sat.angle) * ringRadius;

          // Glowing satellite node
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.arc(satX, satY, sat.size, 0, Math.PI * 2);
          ctx.fillStyle = sat.color;
          ctx.fill();

          // Satellite halo glow
          ctx.beginPath();
          ctx.arc(satX, satY, sat.size * 2.8, 0, Math.PI * 2);
          ctx.fillStyle = sat.glowColor;
          ctx.fill();
        }

        ctx.restore();
      }

      animationFrameRef.current = requestAnimationFrame(render);
    };

    animationFrameRef.current = requestAnimationFrame(render);

    return () => {
      isDestroyed = true;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      resizeObserver.disconnect();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (containerEl) {
        containerEl.removeEventListener('mousemove', handleMouseMove);
        containerEl.removeEventListener('mouseleave', handleMouseLeave);
      }
    };
  }, [size, prefersReducedMotion]);

  return (
    <div
      ref={containerRef}
      className={`relative flex items-center justify-center select-none overflow-visible ${className}`}
      style={{ width: '100%', maxWidth: `${size}px`, aspectRatio: '1 / 1' }}
      aria-label="Animated 3D Particle Intelligence Globe"
      role="img"
    >
      {/* Background ambient diffuse aura */}
      <div className="absolute inset-0 pointer-events-none rounded-full bg-cyan-500/12 blur-[100px] -z-10" />

      {/* Primary 3D Canvas */}
      <canvas
        ref={canvasRef}
        className="w-full h-full block cursor-grab active:cursor-grabbing"
      />
    </div>
  );
}
