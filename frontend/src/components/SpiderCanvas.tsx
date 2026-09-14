'use client'

/**
 * SpiderCanvas — exact port of the Stitch Mission Control canvas animation.
 *
 * Architecture:
 * - Grid of nodes spaced 58px apart, breathing with a gentle organic oscillation
 * - Mouse-tracking nexus: glowing white/cyan hub that draws spider-web rays to
 *   nearby grid nodes (within 260px radius)
 * - Pulsing radar rings emanate from the nexus
 * - Smooth mouse lerp (8% per frame) with ambient drift when idle
 */

import { useEffect, useRef } from 'react'

interface GridNode {
  originX: number
  originY: number
  x: number
  y: number
  baseRadius: number
  currentRadius: number
  phase: number
  speed: number
}

interface Props {
  opacity?: number
}

export default function SpiderCanvas({ opacity = 0.4 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    // ── Sizing ───────────────────────────────────────────────────────────────
    let width  = (canvas.width  = window.innerWidth)
    let height = (canvas.height = window.innerHeight)

    // ── Mouse nexus state ────────────────────────────────────────────────────
    const mouse = {
      x:       width  * 0.55,
      y:       height * 0.42,
      targetX: width  * 0.55,
      targetY: height * 0.42,
      radius:  260,
    }

    // ── Grid nodes ───────────────────────────────────────────────────────────
    const SPACING = 58
    let gridNodes: GridNode[] = []

    function buildGrid() {
      gridNodes = []
      const cols = Math.ceil(width  / SPACING) + 2
      const rows = Math.ceil(height / SPACING) + 2
      for (let c = 0; c < cols; c++) {
        for (let r = 0; r < rows; r++) {
          gridNodes.push({
            originX:       c * SPACING,
            originY:       r * SPACING,
            x:             c * SPACING,
            y:             r * SPACING,
            baseRadius:    (c % 2 === 0 && r % 2 === 0) ? 2.2 : 1.4,
            currentRadius: 1.5,
            phase:         Math.random() * Math.PI * 2,
            speed:         0.015 + Math.random() * 0.02,
          })
        }
      }
    }

    buildGrid()

    // ── Event listeners ──────────────────────────────────────────────────────
    const onResize = () => {
      width  = canvas.width  = window.innerWidth
      height = canvas.height = window.innerHeight
      buildGrid()
    }

    const onMouseMove = (e: MouseEvent) => {
      mouse.targetX = e.clientX
      mouse.targetY = e.clientY
    }

    const onMouseLeave = () => {
      mouse.targetX = width  * 0.52
      mouse.targetY = height * 0.45
    }

    window.addEventListener('resize',      onResize)
    window.addEventListener('mousemove',   onMouseMove)
    window.addEventListener('mouseleave',  onMouseLeave)

    // ── Animation loop ───────────────────────────────────────────────────────
    let frame = 0
    let raf: number

    function animate() {
      frame++

      // Lerp mouse toward target
      mouse.x += (mouse.targetX - mouse.x) * 0.08
      mouse.y += (mouse.targetY - mouse.y) * 0.08

      // Ambient drift
      const effectiveNexusX = mouse.x + Math.cos(frame * 0.01) * 10
      const effectiveNexusY = mouse.y + Math.sin(frame * 0.02) * 15 * 0.5

      ctx.clearRect(0, 0, width, height)

      // 1. Grid nodes + spider-web rays to nexus
      for (let i = 0; i < gridNodes.length; i++) {
        const node = gridNodes[i]

        // Organic breathing oscillation
        const breath = Math.sin(frame * node.speed + node.phase)
        node.x = node.originX + Math.cos(node.phase + frame * 0.01) * 3.5
        node.y = node.originY + Math.sin(node.phase + frame * 0.01) * 3.5

        const dx   = node.x - effectiveNexusX
        const dy   = node.y - effectiveNexusY
        const dist = Math.sqrt(dx * dx + dy * dy)

        if (dist < mouse.radius) {
          const proximity = 1 - dist / mouse.radius
          const alpha     = proximity * 0.55

          // Radiant spider-web line to nexus
          ctx.beginPath()
          ctx.moveTo(effectiveNexusX, effectiveNexusY)
          ctx.lineTo(node.x, node.y)
          ctx.strokeStyle = `rgba(0,229,255,${alpha * 0.7})`
          ctx.lineWidth   = proximity > 0.6 ? 1.2 : 0.75
          ctx.stroke()

          if (proximity > 0.4) {
            ctx.fillStyle          = `rgba(255,255,255,${proximity * 0.9})`
            node.currentRadius = node.baseRadius + proximity * 3.2
          } else {
            ctx.fillStyle          = `rgba(0,229,255,${0.3 + proximity * 0.5})`
            node.currentRadius = node.baseRadius + proximity * 1.5
          }
        } else {
          node.currentRadius = node.baseRadius * (0.8 + 0.2 * breath)
          ctx.fillStyle = (i % 3 === 0)
            ? 'rgba(0,229,255,0.22)'
            : 'rgba(148,163,184,0.18)'
        }

        // Draw node dot
        ctx.beginPath()
        ctx.arc(node.x, node.y, Math.max(0.8, node.currentRadius), 0, Math.PI * 2)
        ctx.fill()
      }

      // 2. Central nexus — radar pulse ring
      ctx.save()
      const pulseRing  = (frame * 0.8) % 70
      const pulseAlpha = Math.max(0, 1 - pulseRing / 70) * 0.35
      ctx.beginPath()
      ctx.arc(effectiveNexusX, effectiveNexusY, pulseRing + 5, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(0,229,255,${pulseAlpha})`
      ctx.lineWidth   = 1
      ctx.stroke()

      // Radial glow
      const grad = ctx.createRadialGradient(
        effectiveNexusX, effectiveNexusY, 0,
        effectiveNexusX, effectiveNexusY, 18,
      )
      grad.addColorStop(0,    'rgba(255,255,255,0.95)')
      grad.addColorStop(0.35, 'rgba(0,229,255,0.8)')
      grad.addColorStop(1,    'rgba(0,229,255,0)')
      ctx.fillStyle = grad
      ctx.beginPath()
      ctx.arc(effectiveNexusX, effectiveNexusY, 18, 0, Math.PI * 2)
      ctx.fill()

      // Core white dot
      ctx.beginPath()
      ctx.arc(effectiveNexusX, effectiveNexusY, 4.2, 0, Math.PI * 2)
      ctx.fillStyle  = '#FFFFFF'
      ctx.shadowColor = '#00E5FF'
      ctx.shadowBlur  = 12
      ctx.fill()
      ctx.restore()

      raf = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize',     onResize)
      window.removeEventListener('mousemove',  onMouseMove)
      window.removeEventListener('mouseleave', onMouseLeave)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{ opacity, position: 'fixed', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  )
}
