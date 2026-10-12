import { useState, useEffect } from 'react'

export interface MissionEntry {
  time: string
  lat: number | null
  lon: number | null
  people: number
  damage: Array<{ type: string; confidence: number }>
  spills: Array<{ type: string; confidence: number }>
}

export function useMissionLog(pollInterval = 3000) {
  const [log, setLog] = useState<MissionEntry[]>([])
  const [lastEntry, setLastEntry] = useState<MissionEntry | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const r = await fetch('/mission_log.json', { cache: 'no-store' })
        if (!r.ok) return
        const data: MissionEntry[] = await r.json()
        setLog(data)
        setLastEntry(data.length > 0 ? data[data.length - 1] : null)
      } catch {}
    }
    load()
    const id = setInterval(load, pollInterval)
    return () => clearInterval(id)
  }, [pollInterval])

  return {
    log,
    lastEntry,
    people:      lastEntry?.people ?? 0,
    damage:      lastEntry?.damage.length ?? 0,
    spills:      lastEntry?.spills.length ?? 0,
    totalEvents: log.length,
  }
}
