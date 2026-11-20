// Small fetch wrapper. All writes are idempotent on the server, so we can
// safely retry them on flaky bar Wi-Fi.

function safeGet(k) { try { return localStorage.getItem(k) } catch { return null } }
function safeSet(k, v) { try { localStorage.setItem(k, v) } catch { /* ignore */ } }

export function deviceId() {
  let id = safeGet('hh_device')
  if (!id) {
    id = 'd-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    safeSet('hh_device', id)
  }
  return id
}

export const hostKey = {
  get: (code) => safeGet(`hh_host_${code}`),
  set: (code, key) => safeSet(`hh_host_${code}`, key),
}

export class ApiError extends Error {
  constructor(code, status) { super(code); this.code = code; this.status = status }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export async function api(path, { method = 'GET', body, key, retries = method === 'GET' ? 0 : 3 } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (key) headers['X-Host-Key'] = key
  let lastErr
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const ctl = new AbortController()
      const timer = setTimeout(() => ctl.abort(), 6000)
      const res = await fetch(`/api${path}`, {
        method, headers, body: body ? JSON.stringify(body) : undefined, signal: ctl.signal,
      })
      clearTimeout(timer)
      let data = null
      try { data = await res.json() } catch { data = null }
      if (!res.ok) throw new ApiError(data?.error || 'generic', res.status)
      return data
    } catch (e) {
      lastErr = e
      if (e instanceof ApiError && e.status < 500) throw e // real answer from server: don't retry
      if (attempt < retries) await sleep(400 * 2 ** attempt)
    }
  }
  throw lastErr instanceof ApiError ? lastErr : new ApiError('offline', 0)
}

// Turn any error into an i18n key the UI can show (never a raw error).
export function errKey(e) {
  const code = e?.code || 'generic'
  const known = ['room_not_found', 'room_full', 'name_required', 'not_host', 'answers_locked',
    'question_moved_on', 'too_fast', 'offline', 'roast_off', 'not_mic_ready', 'max_six', 'own_answer',
    'text_required', 'too_late', 'bad_question', 'viral_not_ready', 'viral_wrong_time']
  return known.includes(code) ? `err_${code}` : 'err_generic'
}
