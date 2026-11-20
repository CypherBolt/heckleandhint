// Tier 3 host panels: live content status, "This Week in Saigon" drafts, Viral Drop.
import { useState } from 'react'
import { api, errKey } from '../api'
import { Countdown, OPTION_STYLES } from '../components'
import { pick, useLang } from '../i18n'
import { Num, toast } from '../ui'

function StatusChip({ on, label }) {
  const { t } = useLang()
  return (
    <span className={`live-chip ${on ? 'on' : ''}`}>
      <span className="dot" aria-hidden /> {label}: <b>{on ? t('live_on') : t('live_backup')}</b>
    </span>
  )
}

function SourceLink({ source }) {
  const { t } = useLang()
  if (!source?.url) return null
  let host = ''
  try { host = new URL(source.url).hostname.replace(/^www\./, '') } catch { host = source.url }
  return (
    <a className="source-link" href={source.url} target="_blank" rel="noreferrer">📰 {t('source')}: {source.title || host} <span className="muted">({host})</span></a>
  )
}

export function LiveContentPanel({ s, code, hostKey, act, setState }) {
  const { t, lang } = useLang()
  const [busy, setBusy] = useState(null)
  const fetchLive = async (kind) => {
    setBusy(kind)
    try {
      const v = await api(`/rooms/${code}/live/${kind}`, { method: 'POST', key: hostKey })
      setState(v)
    } catch (e) {
      toast.error(t(errKey(e)))
    } finally {
      setBusy(null)
    }
  }
  const weeklyWorking = s.weekly?.status === 'working' || busy === 'weekly'
  const viralWorking = s.viral?.status === 'working' || busy === 'viral'
  const cards = s.viral?.cards || []
  return (
    <div className="panel live-panel">
      <h3>📡 {t('live_title')}</h3>
      <div className="row" style={{ gap: 6 }}>
        <StatusChip on={s.live?.ai} label={t('live_ai')} />
        <StatusChip on={s.live?.search} label={t('live_search')} />
      </div>
      {!(s.live?.ai && s.live?.search) && <p className="hint">{t('live_help')}</p>}

      {/* ---- This Week in Saigon */}
      <div className="live-block">
        <h4>🗞️ {t('weekly_title')}</h4>
        <p className="hint" style={{ marginTop: 0 }}>{t('weekly_help')}</p>
        <button className="btn yellow block" disabled={weeklyWorking} onClick={() => fetchLive('weekly')}>
          {weeklyWorking ? `⏳ ${t('weekly_working')}` : s.weekly?.status === 'ready' ? `↻ ${t('weekly_refetch')}` : `✨ ${t('weekly_fetch')}`}
        </button>
        {s.weekly?.status === 'ready' && (
          <p className="origin-note">{s.weekly.origin === 'live' ? `🟢 ${t('weekly_live')}` : `🟡 ${t('weekly_backup')}`}</p>
        )}
        {s.weekly?.status === 'ready' && s.drafts.length === 0 && <p className="muted">{t('weekly_empty')}</p>}
        {s.drafts.map((d) => (
          <div className="draft" key={d.id}>
            <b>{pick(d.text, lang)}</b>
            <ol className="draft-opts">
              {d.options.map((o, i) => (
                <li key={i} className={i === d.correct ? 'right' : ''}>{OPTION_STYLES[i].shape} {pick(o, lang)}{i === d.correct ? ' ✅' : ''}</li>
              ))}
            </ol>
            <SourceLink source={d.source} />
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn small lime" onClick={async () => { if (await act('draft', { draft_id: d.id, op: 'approve' })) toast.success(t('draft_added')) }}>
                ✓ {t('btn_approve')}
              </button>
              <button className="btn small" onClick={() => act('draft', { draft_id: d.id, op: 'reject' })}>✕ {t('btn_reject')}</button>
            </div>
          </div>
        ))}
      </div>

      {/* ---- Viral Drop */}
      <div className="live-block">
        <h4>🔥 {t('viral_title')}</h4>
        <p className="hint" style={{ marginTop: 0 }}>{t('viral_help')}</p>
        <button className="btn block" disabled={viralWorking} onClick={() => fetchLive('viral')}>
          {viralWorking ? `⏳ ${t('viral_working')}` : cards.length ? `🔀 ${t('viral_shuffle')}` : `🔎 ${t('viral_fetch')}`}
        </button>
        {cards.length > 0 && !viralWorking && (
          <>
            {cards.map((c, i) => (
              <div className="viral-card-host" key={i} style={{ borderLeftColor: OPTION_STYLES[i].color }}>
                <b>{OPTION_STYLES[i].shape} {c.title}</b>
                <p style={{ margin: '4px 0' }}>{c.text}</p>
                <p className="muted credit">{t('credit')} {c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.credit}</a> : c.credit}</p>
                <details>
                  <summary>🤫 {t('viral_angles')}</summary>
                  <ul>{c.angles.map((a, k) => <li key={k}>{a}</li>)}</ul>
                </details>
              </div>
            ))}
            {s.viral_can_send
              ? <button className="btn pink block" style={{ marginTop: 10 }} onClick={() => act('viral_send')}>{t('viral_send')}</button>
              : <p className="hint">⏸ {t('viral_when')}</p>}
          </>
        )}
      </div>
    </div>
  )
}

// While a Viral Drop is running: what the comedian needs, in order of urgency.
export function ViralHostPanel({ s, serverNow }) {
  const { t } = useLang()
  const v = s.viral || {}
  const cards = v.cards || []
  const win = v.winner != null ? cards[v.winner] : null
  return (
    <div className="panel prompter viral-host">
      <div className="row">
        <h3 className="grow" style={{ margin: 0 }}>🔥 {t('viral_tag')} · {t(`phase_${s.phase}`)}</h3>
        {['viral_vote', 'viral_rate', 'viral_result'].includes(s.phase) && <b>{s.answered_count}/{s.team_count}</b>}
      </div>
      {['viral_vote', 'viral_riff', 'viral_rate'].includes(s.phase) && <Countdown state={{ ...s, question: { time_limit: s.phase === 'viral_riff' ? 60 : 15 } }} serverNow={serverNow} />}
      {s.phase === 'viral_vote' && cards.map((c, i) => (
        <div className="row" key={i} style={{ justifyContent: 'space-between', marginTop: 6 }}>
          <span>{OPTION_STYLES[i].shape} {c.title}</span><b><Num value={v.counts?.[i] || 0} /></b>
        </div>
      ))}
      {win && (
        <>
          <p className="muted" style={{ margin: '8px 0 0' }}>{t('viral_winner')}:</p>
          <div className="q">{win.title}</div>
          <p className="line punch" style={{ marginTop: 0 }}><small>🤫 {t('viral_angles')}</small></p>
          <ol className="angles">{win.angles.map((a, k) => <li key={k}>{a}</li>)}</ol>
          <p className="muted" style={{ fontSize: 14 }}>{win.text}</p>
        </>
      )}
      {['viral_rate', 'viral_result'].includes(s.phase) && (
        <p className="viral-rating">⭐ {v.rating != null ? <Num value={v.rating} /> : '–'} <span className="muted">· {t('viral_ratings', { n: v.rated || 0 })}</span></p>
      )}
    </div>
  )
}

export { SourceLink }
