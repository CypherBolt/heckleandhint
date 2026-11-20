import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

// Polls GET /api/rooms/{code}/state every 1.5 s. Sends the last version we saw;
// the server answers "unchanged" when nothing happened (tiny response).
export function usePoll(code, role, { device, hostKey, enabled = true } = {}) {
  const [state, setState] = useState(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState(null)
  const versionRef = useRef(null)
  const offsetRef = useRef(0) // server clock - local clock
  const fails = useRef(0)

  const apply = useCallback((data) => {
    if (!data) return
    if (data.server_now) offsetRef.current = data.server_now - Date.now()
    if (data.unchanged) return
    // Never go backwards: a slow poll that left before a write can arrive after it.
    if (versionRef.current != null && data.version < versionRef.current) return
    versionRef.current = data.version
    setState(data)
  }, [])

  const refresh = useCallback(async () => {
    const qs = new URLSearchParams({ role })
    if (versionRef.current != null) qs.set('since', versionRef.current)
    if (device) qs.set('device', device)
    try {
      const data = await api(`/rooms/${code}/state?${qs}`, { key: hostKey })
      fails.current = 0
      setOffline(false)
      setError(null)
      apply(data)
    } catch (e) {
      if (e.status === 404 || e.status === 403) { setError(e.code); return }
      fails.current += 1
      if (fails.current >= 2) setOffline(true)
    }
  }, [code, role, device, hostKey, apply])

  useEffect(() => {
    if (!enabled) return
    let alive = true
    let timer
    const loop = async () => {
      await refresh()
      if (alive) timer = setTimeout(loop, 1500)
    }
    loop()
    return () => { alive = false; clearTimeout(timer) }
  }, [refresh, enabled])

  // Force a full refresh (e.g. right after a write) by forgetting the version.
  const forceRefresh = useCallback(() => {
    const keep = versionRef.current
    versionRef.current = null
    return refresh().finally(() => { if (versionRef.current == null) versionRef.current = keep })
  }, [refresh])

  const serverNow = useCallback(() => Date.now() + offsetRef.current, [])
  return { state, setState: apply, offline, error, refresh: forceRefresh, serverNow }
}

// Re-render every `ms` (used for countdowns and rotating copy).
export function useTicker(ms = 250) {
  const [, setN] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setN((n) => n + 1), ms)
    return () => clearInterval(id)
  }, [ms])
}
