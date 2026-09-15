'use client'

import { useEffect, useRef } from 'react'

const NODE_COLORS: Record<string, string> = {
  Phone:    '#10B981',
  Account:  '#F59E0B',
  Device:   '#00E5FF',
  Tower:    '#94A3B8',
  Document: '#A855F7',
}
const EDGE_COLORS: Record<string, string> = {
  CALLED:             '#00E5FF',
  TRANSFERRED_TO:     '#F59E0B',
  USED_DEVICE:        '#94A3B8',
  CONNECTED_TO_TOWER: '#475569',
}

interface CyNode {
  id: string
  labels?: string[]
  normalized_number?: string
  normalized_identifier?: string
  [k: string]: unknown
}
interface CyEdge {
  id: string
  source?: string
  target?: string
  relationship_type?: string
  [k: string]: unknown
}

interface CytoscapeCanvasProps {
  nodes: CyNode[]
  edges: CyEdge[]
  onNodeClick?: (node: CyNode) => void
  onEdgeClick?: (edgeId: string) => void
}

export default function CytoscapeCanvas({
  nodes,
  edges,
  onNodeClick,
  onEdgeClick,
}: CytoscapeCanvasProps) {
  const containerRef  = useRef<HTMLDivElement>(null)
  const cyRef         = useRef<unknown>(null)

  // Keep callbacks in refs so Cytoscape event handlers never go stale
  // and we never need to re-initialise the graph just because a prop changed
  const onNodeClickRef = useRef(onNodeClick)
  const onEdgeClickRef = useRef(onEdgeClick)
  useEffect(() => { onNodeClickRef.current = onNodeClick }, [onNodeClick])
  useEffect(() => { onEdgeClickRef.current = onEdgeClick }, [onEdgeClick])

  useEffect(() => {
    if (!containerRef.current) return

    let destroyed = false

    const init = async () => {
      const { default: cytoscape } = await import('cytoscape')

      // Register fcose layout once
      try {
        const { default: fcose } = await import('cytoscape-fcose')
        const cy = cytoscape as unknown as { fcoseRegistered?: boolean; use: (ext: unknown) => void }
        if (!cy.fcoseRegistered) {
          cy.use(fcose)
          cy.fcoseRegistered = true
        }
      } catch { /* layout optional */ }

      if (destroyed) return

      const elements = [
        ...nodes.map((n) => {
          const label = Array.isArray(n.labels) ? n.labels[0] ?? 'Node' : 'Node'
          const displayId = String(n.normalized_number ?? n.normalized_identifier ?? n.id ?? '').slice(0, 20)
          return {
            group: 'nodes' as const,
            data: { id: String(n.id ?? displayId), label: displayId, entity: label, raw: n },
          }
        }),
        ...edges
          .map((e) => {
            const raw = e as Record<string, unknown>
            const isCandidate = Boolean(raw.is_candidate)
            return {
              group: 'edges' as const,
              data: {
                id: String(e.id ?? Math.random()),
                source: String(raw.source ?? ''),
                target: String(raw.target ?? ''),
                label: (e.relationship_type as string) ?? (isCandidate ? 'Potential Association' : ''),
                is_candidate: isCandidate ? 'true' : 'false',
                raw: e,
              },
            }
          })
          .filter((e) => e.data.source && e.data.target),
      ]

      // Destroy previous instance
      if (cyRef.current) {
        (cyRef.current as { destroy: () => void }).destroy()
      }

      const cy = cytoscape({
        container: containerRef.current!,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': (ele: unknown) =>
                NODE_COLORS[(ele as { data: (k: string) => string }).data('entity')] ?? '#475569',
              'label': 'data(label)',
              'color': '#CBD5E1',
              'font-size': '9px',
              'font-family': 'JetBrains Mono, monospace',
              'text-valign': 'bottom',
              'text-margin-y': 5,
              'width': 26,
              'height': 26,
              'border-width': 2,
              'border-color': (ele: unknown) =>
                NODE_COLORS[(ele as { data: (k: string) => string }).data('entity')] ?? '#475569',
              'border-opacity': 0.7,
            },
          },
          {
            selector: 'node:selected',
            style: {
              'border-width': 3.5,
              'border-color': '#00E5FF',
              'background-color': '#00E5FF',
              'color': '#FFFFFF',
            },
          },
          {
            selector: 'edge',
            style: {
              'width': 1.2,
              'line-color': (ele: unknown) =>
                EDGE_COLORS[(ele as { data: (k: string) => string }).data('label')] ?? '#334155',
              'target-arrow-color': (ele: unknown) =>
                EDGE_COLORS[(ele as { data: (k: string) => string }).data('label')] ?? '#334155',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'opacity': 0.65,
            },
          },
          {
            selector: 'edge[is_candidate = "true"]',
            style: {
              'width': 2.0,
              'line-color': '#A855F7',
              'line-style': 'dashed',
              'target-arrow-color': '#A855F7',
              'target-arrow-shape': 'triangle',
              'opacity': 0.85,
            },
          },
          {
            selector: 'edge:selected',
            style: {
              'width': 2.5,
              'line-color': '#00E5FF',
              'target-arrow-color': '#00E5FF',
              'opacity': 1,
            },
          },
          {
            selector: 'edge[is_candidate = "true"]:selected',
            style: {
              'width': 3.0,
              'line-color': '#C084FC',
              'target-arrow-color': '#C084FC',
              'opacity': 1.0,
            },
          },
        ],
        layout: {
          name: nodes.length > 0 ? 'fcose' : 'grid',
          animate: true,
          animationDuration: 500,
          nodeSeparation: 100,
          idealEdgeLength: 90,
          padding: 40,
          randomize: false,
        } as any,
        userZoomingEnabled: true,
        userPanningEnabled: true,
      })

      // Use stable ref callbacks — these never cause cy re-init
      cy.on('tap', 'node', (evt: unknown) => {
        const ele = (evt as { target: { data: (k: string) => unknown } }).target
        onNodeClickRef.current?.(ele.data('raw') as CyNode)
      })

      cy.on('tap', 'edge', (evt: unknown) => {
        const ele = (evt as { target: { data: (k: string) => unknown } }).target
        const raw = ele.data('raw') as CyEdge
        onEdgeClickRef.current?.(String(raw.id ?? ele.data('id')))
      })

      cyRef.current = cy
    }

    init()

    return () => {
      destroyed = true
      if (cyRef.current) {
        (cyRef.current as { destroy: () => void }).destroy()
        cyRef.current = null
      }
    }
  // Only re-run when nodes/edges change (i.e. when graphKey changes in parent)
  // onNodeClick / onEdgeClick are handled via refs above
  }, [nodes, edges]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={containerRef} className="w-full h-full" />
}
