import { useEffect, useRef, useState } from 'react'
import { ROTATING, useLang } from './i18n'
import { useTicker } from './usePoll'
import { Num, toast } from './ui'

export const OPTION_STYLES = [
  { color: 'var(--opt-red)', shape: '▲' },
  { color: 'var(--opt-blue)', shape: '◆' },
  { color: 'var(--opt-yellow)', shape: '●' },
  { color: 'var(--opt-green)', shape: '■' },
]

export function LangToggle({ className = '' }) {
  const { lang, setLang } = useLang()
  return (
    <div className={`lang-toggle ${className}`} role="group" aria-label="Language">
      <button className={lang === 'vi' ? 'on' : ''} onClick={() => setLang('vi')} aria-pressed={lang === 'vi'}>VI</button>
      <span aria-hidden>|</span>
      <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')} aria-pressed={lang === 'en'}>EN</button>
    </div>
  )
}

export function Reconnecting({ show }) {
  const { t } = useLang()
  if (!show) return null
  return <div className="reconnecting" role="status">📡 {t('reconnecting')}</div>
}

export function Rotator({ set, every = 4000, lang: forced }) {
  const { lang } = useLang()
  const l = forced || lang
  const lines = ROTATING[set][l]
  const [i, setI] = useState(() => Math.floor(Math.random() * lines.length))
  useEffect(() => {
    const id = setInterval(() => setI((x) => (x + 1) % lines.length), every)
    return () => clearInterval(id)
  }, [lines.length, every])
  return <p className="rotator" key={`${l}-${i}`}>{lines[i % lines.length]}</p>
}

export function secondsLeft(state, serverNow) {
  if (!state) return 0
  if (state.frozen) return Math.ceil((state.frozen_remaining || 0) / 1000)
  if (!state.phase_ends_at) return 0
  return Math.max(0, Math.ceil((state.phase_ends_at - serverNow()) / 1000))
}

export function Countdown({ state, serverNow, big = false }) {
  useTicker(250)
  const { t } = useLang()
  const left = secondsLeft(state, serverNow)
  const limit = state?.question?.time_limit || 20
  const pct = Math.min(100, (left / limit) * 100)
  return (
    <div className={`countdown ${big ? 'big' : ''} ${left <= 5 && !state.frozen ? 'urgent' : ''}`}>
      <span className="count-num">{state.frozen ? `⏸ ${t('frozen')}` : <Num value={left} />}</span>
      <div className="count-bar"><div style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

export function teamLabel(team, t) {
  if (!team) return ''
  return team.name || t('team_n', { n: team.n })
}

// Errors and confirmations go through Sonner (see ui.jsx). Kept as a component so
// callers can keep the simple `<Toast msg=... onDone=... />` pattern.
export function Toast({ msg, onDone, kind = 'error' }) {
  const done = useRef(onDone)
  done.current = onDone
  useEffect(() => {
    if (!msg) return
    ;(kind === 'success' ? toast.success : toast.error)(msg)
    done.current()
  }, [msg, kind])
  return null
}

// ---------------------------------------------------------------- Tier 2 helpers
// Laugh meter: laughs in the last 3 s, scaled by how many teams are in the room.
export function laughLevel(reactLog, serverNow, teamCount) {
  const now = serverNow()
  let laughs = 0
  for (const [t, l] of reactLog || []) if (now - t <= 3000 && now - t >= -1000) laughs += l
  const perTeam = laughs / Math.max(1, teamCount)
  const frac = Math.min(1, perTeam / 6)
  const idx = frac < 0.12 ? 0 : frac < 0.3 ? 1 : frac < 0.5 ? 2 : frac < 0.7 ? 3 : frac < 0.9 ? 4 : 5
  return { frac, idx, laughs }
}

export function LaughMeter({ reactLog, serverNow, teamCount, compact = false }) {
  useTicker(200)
  const { t, t2 } = useLang()
  const { frac, idx } = laughLevel(reactLog, serverNow, teamCount)
  const hue = 90 - frac * 90 // lime -> red
  return (
    <div className={`laugh-meter ${compact ? 'compact' : ''} ${idx === 5 ? 'max' : ''}`} aria-label={t('laugh_meter')}>
      <div className="lm-label">😂</div>
      <div className="lm-tube"><div className="lm-fill" style={{ height: `${Math.max(3, frac * 100)}%`, background: `hsl(${hue} 85% 55%)` }} /></div>
      <div className="lm-text">{t(`meter_${idx}`)}{!compact && <span className="sec"> / {t2(`meter_${idx}`)}</span>}</div>
    </div>
  )
}

// Effects (style points, roast cards, spotlight, heckles) are active until `until`.
export function useActiveEffects(effects, serverNow) {
  useTicker(250)
  const now = serverNow()
  return (effects || []).filter((e) => e.at <= now + 1000 && e.until > now)
}

export function newId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

export function Follow({ profile, code }) {
  const { t } = useLang()
  const p = profile || {}
  const handle = (v) => v.replace(/^@/, '')
  const link = (kind, v) => {
    if (/^https?:\/\//i.test(v)) return v
    if (kind === 'zalo') return `https://zalo.me/${handle(v)}`
    if (kind === 'facebook') return `https://facebook.com/${handle(v)}`
    if (kind === 'instagram') return `https://instagram.com/${handle(v)}`
    return `https://www.tiktok.com/@${handle(v)}`
  }
  const items = [['zalo', 'Zalo', '💬'], ['facebook', 'Facebook', '📘'], ['instagram', 'Instagram', '📸'], ['tiktok', 'TikTok', '🎵']]
    .filter(([k]) => p[k])
  const recapUrl = `${window.location.origin}/recap/${code}`
  const share = async () => {
    try {
      if (navigator.share) { await navigator.share({ title: 'Heckle & Hint', url: recapUrl }); return }
      await navigator.clipboard.writeText(recapUrl)
      toast.success(t('copied'))
    } catch { /* user cancelled */ }
  }
  return (
    <div className="panel follow-card">
      <h3>👋 {t('follow_title')}</h3>
      {p.host_name && <p style={{ fontSize: 24, fontWeight: 900, margin: '4px 0' }}>🎤 {p.host_name}</p>}
      <p className="muted" style={{ marginTop: 0 }}>{t('follow_sub')}</p>
      <div className="follow-links">
        {items.map(([k, label, icon]) => (
          <a key={k} className="btn block" href={link(k, p[k])} target="_blank" rel="noreferrer">{icon} {label}: {p[k]}</a>
        ))}
      </div>
      <button className="btn pink block" style={{ marginTop: 10 }} onClick={share}>🔗 {t('share_night')}</button>
    </div>
  )
}
