import { useState, useEffect } from 'react'

export interface DetectionState {
  timestamp: string
  source:    string
  people:    number
  rubble:    number
  spills:    number
  fps:       number
}

const EMPTY: DetectionState = { timestamp: '', source: '', people: 0, rubble: 0, spills: 0, fps: 0 }

export function useDetectionState(pollMs = 1000) {
  const [state, setState] = useState<DetectionState | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const r = await fetch('/detection_state.json', { cache: 'no-store' })
        if (r.ok) setState(await r.json())
      } catch {}
    }
    load()
    const id = setInterval(load, pollMs)
    return () => clearInterval(id)
  }, [pollMs])

  return state ?? EMPTY
}
