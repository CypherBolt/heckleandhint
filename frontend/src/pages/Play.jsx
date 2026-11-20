import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, deviceId, errKey } from '../api'
import {
  Countdown, Follow, LangToggle, OPTION_STYLES, Reconnecting, Rotator, Toast, newId, teamLabel, useActiveEffects,
} from '../components'
import { pick, useLang } from '../i18n'
import { usePoll } from '../usePoll'
import { CountUp, Num, Segmented, Sheet, burst } from '../ui'

const ACTION_BAR_PHASES = ['question_locked', 'reveal', 'riff', 'scoreboard', 'wager', 'awards', 'podium', 'viral_riff', 'viral_result']

export default function Play() {
  const { code: raw } = useParams()
  const code = raw.toUpperCase()
  const { t, lang } = useLang()
  const nav = useNavigate()
  const device = deviceId()
  const { state, setState, offline, error, serverNow } = usePoll(code, 'player', { device })
  const [pending, setPending] = useState(null) // optimistic choice while the request flies
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => {
    if (state && !state.me) nav(`/join/${code}`, { replace: true })
  }, [state, code, nav])
  useEffect(() => { setPending(null) }, [state?.q_index, state?.phase])
  useEffect(() => { if (state?.phase === 'ended') burst('big') }, [state?.phase])

  const post = useCallback(async (path, body) => {
    try {
      const s = await api(`/rooms/${code}/${path}`, { method: 'POST', body: { device_id: device, ...body } })
      if (s && s.role === 'player') setState(s)
      return s
    } catch (e) {
      setErr(t(errKey(e)))
      return null
    }
  }, [code, device, setState, t])

  if (error === 'room_not_found') {
    return (
      <div className="page center"><div className="big-emoji">🤷</div><p>{t('err_room_not_found')}</p>
        <button className="btn yellow" onClick={() => nav('/')}>{t('go_home')}</button></div>
    )
  }
  if (!state || !state.me) return <div className="page center muted">{t('loading')}</div>

  const { me, phase, question: q, my_answer: mine } = state
  const choice = mine?.choice ?? pending

  const answer = async (i) => {
    if (choice != null) return
    setPending(i)
    const s = await post('answer', { q_index: q.i, choice: i })
    if (!s) setPending(null)
  }

  const header = (
    <div className="topbar">
      <span className="row" style={{ gap: 8, fontWeight: 800, flexWrap: 'nowrap', minWidth: 0 }}>
        <span style={{ fontSize: 26 }}>{me.emoji}</span>
        <span style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{me.name}</span>
      </span>
      <span className="muted" style={{ fontWeight: 800, whiteSpace: 'nowrap' }}><Num value={me.total} /> · #{me.rank}</span>
      <LangToggle />
    </div>
  )

  let body
  if (phase === 'lobby') {
    body = (
      <div className="play-main center" style={{ justifyContent: 'center' }}>
        <div className="big-emoji">{me.emoji}</div>
        <h1 style={{ color: 'var(--lime)' }}>{t('you_are_in')}</h1>
        <h2>{me.name}</h2>
        {me.name_status === 'pending' && <p className="badge-warn" style={{ padding: 8 }}>{t('pending_name')}</p>}
        <p>{t('waiting_for_host')}</p>
        <Rotator set="lobby" />
      </div>
    )
  } else if (phase === 'question_open' && q && q.type === 'writein') {
    body = <WriteIn q={q} mine={mine} state={state} serverNow={serverNow} post={post} />
  } else if (phase === 'question_open' && q) {
    if (choice == null) {
      body = (
        <div className="play-main">
          <QHead q={q} state={state} />
          <h2 style={{ fontSize: 22, marginTop: 10 }}>{pick(q.text, lang)}</h2>
          {state.wager && <p className="badge-warn" style={{ padding: 6 }}>💰 {t('wager_locked', { n: state.wager.bet })}</p>}
          <Countdown state={state} serverNow={serverNow} />
          <div className="answer-grid">
            {q.options.map((o, i) => (
              <button key={i} className="answer-btn" style={{ background: OPTION_STYLES[i].color }} onClick={() => answer(i)}
                aria-label={pick(o, lang)}>
                <span className="shape" aria-hidden>{OPTION_STYLES[i].shape}</span>
                <span>{pick(o, lang)}</span>
              </button>
            ))}
          </div>
        </div>
      )
    } else {
      body = <LockedIn q={q} choice={choice} state={state} serverNow={serverNow} />
    }
  } else if (phase === 'question_locked') {
    body = (
      <div className="play-main center" style={{ justifyContent: 'center' }}>
        <div className="big-emoji">🔒</div>
        <h1>{t('answers_locked')}</h1>
        {choice != null && q && <ChoicePill q={q} choice={choice} />}
        {mine?.text && <p className="writein-mine">“{mine.text}”</p>}
        <p>{t('host_reading')}</p>
        <Rotator set="locked" />
      </div>
    )
  } else if (phase === 'vote' && q) {
    body = <Vote q={q} state={state} serverNow={serverNow} post={post} />
  } else if (['reveal', 'riff', 'scoreboard'].includes(phase) && q && q.type === 'writein') {
    body = <WriteInResult q={q} state={state} phase={phase} />
  } else if (['reveal', 'riff', 'scoreboard'].includes(phase) && q) {
    body = <Result q={q} mine={mine} me={me} state={state} phase={phase} />
  } else if (phase.startsWith('viral_')) {
    body = <ViralPhone state={state} post={post} serverNow={serverNow} />
  } else if (phase === 'wager') {
    body = <Wager state={state} post={post} />
  } else if (phase === 'awards' || phase === 'podium') {
    body = <AwardsPhone state={state} />
  } else if (phase === 'ended') {
    body = (
      <div className="play-main center">
        <div className="big-emoji">🎉</div>
        <h1 style={{ color: 'var(--pink)' }}>{t('night_over')}</h1>
        <p style={{ fontSize: 22, margin: 0 }}>{t('final_rank')}: <b>#{me.rank}</b> {t('of')} {state.team_count}</p>
        <Stats me={me} />
        <Follow profile={state.profile} code={code} />
        <AwardsList awards={state.awards} />
      </div>
    )
  } else {
    body = <div className="play-main center muted">{t('loading')}</div>
  }

  return (
    <div className="play">
      <Reconnecting show={offline} />
      {header}
      {body}
      {ACTION_BAR_PHASES.includes(phase) && <ActionBar code={code} device={device} onNote={setNote} onError={setErr} />}
      <PhoneEffects state={state} serverNow={serverNow} />
      <Toast msg={err} onDone={() => setErr('')} />
      <Toast msg={note} kind="success" onDone={() => setNote('')} />
    </div>
  )
}

function QHead({ q, state }) {
  const { t } = useLang()
  return (
    <div className="row">
      <span className="tag" style={{ color: q.final ? 'var(--pink)' : 'var(--yellow)' }}>
        {q.final ? t('final_tag') : q.type === 'poll' ? t('poll_tag') : q.type === 'writein' ? t('writein_tag')
          : t('question_x_of_y', { x: q.i + 1, y: state.q_total })}
      </span>
      <span className="muted">{t('answered_x', { x: state.answered_count, y: state.team_count })}</span>
    </div>
  )
}


function ChoicePill({ q, choice }) {
  const { lang } = useLang()
  const s = OPTION_STYLES[choice]
  return (
    <div className="answer-btn" style={{ background: s.color, minHeight: 0, flexDirection: 'row', margin: '12px auto', padding: '10px 18px' }}>
      <span className="shape" style={{ fontSize: 28 }}>{s.shape}</span>
      <span>{pick(q.options[choice], lang)}</span>
    </div>
  )
}

function LockedIn({ q, choice, state, serverNow }) {
  const { t } = useLang()
  return (
    <div className="play-main center" style={{ justifyContent: 'center' }}>
      <div className="big-emoji" style={{ color: OPTION_STYLES[choice].color }}>{OPTION_STYLES[choice].shape}</div>
      <h1 style={{ color: 'var(--yellow)' }}>{t('locked_in')}</h1>
      <p className="muted">{t('you_picked')}</p>
      <ChoicePill q={q} choice={choice} />
      <Countdown state={state} serverNow={serverNow} />
      <p className="muted">{t('answered_x', { x: state.answered_count, y: state.team_count })}</p>
      <Rotator set="waiting" />
    </div>
  )
}

function Stats({ me }) {
  const { t } = useLang()
  return (
    <div className="me-stats" style={{ width: '100%', maxWidth: 360, margin: '12px auto 0' }}>
      <div>🧠 {t('brain_points')}<b><Num value={me.brain} /></b></div>
      <div>😂 {t('laugh_points')}<b><Num value={me.laugh} /></b></div>
      <div>{t('total')}<b><Num value={me.total} /></b></div>
    </div>
  )
}

function Result({ q, mine, me, state, phase }) {
  const { t, tn } = useLang()
  let cls, title, sub
  if (q.type === 'poll') {
    cls = 'poll'; title = t('poll_done'); sub = t('poll_sub')
  } else if (!mine) {
    cls = 'neutral'; title = t('too_slow'); sub = t('too_slow_sub')
  } else if (mine.correct) {
    cls = 'correct'; title = t('correct')
  } else {
    cls = 'wrong'; title = t('wrong')
  }
  const wd = state.wager_delta
  useEffect(() => { if (cls === 'correct') burst() }, [cls, q.i])
  return (
    <div className={`result ${cls}`}>
      <div className="big-emoji">{cls === 'correct' ? '🎯' : cls === 'wrong' ? '💀' : cls === 'poll' ? '🗳️' : '😴'}</div>
      <h1>{title}</h1>
      {sub && <p style={{ fontSize: 20 }}>{sub}</p>}
      {mine && q.type !== 'poll' && <div className="pts"><CountUp value={mine.points} plus /></div>}
      {mine && q.type !== 'poll' && <p>{t('points')}{me.streak > 1 ? ` · 🔥 ${t('streak')} ${me.streak}` : ''}</p>}
      {q.final && wd !== undefined && wd !== 0 && (
        <p style={{ fontSize: 28, fontWeight: 900 }}>💰 {tn('wager_result', { n: <CountUp value={wd} plus /> })}</p>
      )}
      <p style={{ fontSize: 24, fontWeight: 900 }}>{t('rank')} #{me.rank} {t('of')} {state.team_count}</p>
      {phase === 'riff' && <p><b>🎤 {t('riff_time')}</b> — {t('riff_sub')}</p>}
      <Stats me={me} />
      {q.source?.url && <a className="phone-source" href={q.source.url} target="_blank" rel="noreferrer">📰 {t('source')}: {q.source.title}</a>}
    </div>
  )
}

function WriteIn({ q, mine, state, serverNow, post }) {
  const { t, lang } = useLang()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const send = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    await post('answer', { q_index: q.i, text })
    setBusy(false)
  }
  return (
    <div className="play-main">
      <QHead q={q} state={state} />
      <h2 style={{ fontSize: 22, marginTop: 10 }}>{pick(q.text, lang)}</h2>
      <Countdown state={state} serverNow={serverNow} />
      {mine ? (
        <div className="center" style={{ marginTop: 24 }}>
          <div className="big-emoji">✍️</div>
          <h2 style={{ color: 'var(--yellow)' }}>{t('locked_in')}</h2>
          <p className="writein-mine">“{mine.text}”</p>
          <p className="muted">{t('writein_sent')}</p>
        </div>
      ) : (
        <form onSubmit={send} style={{ marginTop: 16 }}>
          <textarea className="input" rows={3} maxLength={80} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={t('writein_ph')} aria-label={t('writein_ph')} />
          <p className="hint">{t('chars_left', { n: 80 - text.length })} · {t('fact_note')}</p>
          <button className="btn pink block" type="submit" disabled={busy || !text.trim()} style={{ marginTop: 10 }}>✍️ {t('writein_send')}</button>
        </form>
      )}
    </div>
  )
}

function Vote({ q, state, serverNow, post }) {
  const { t, lang } = useLang()
  const [picked, setPicked] = useState(null)
  const voted = state.my_vote || picked
  const mineSet = new Set(state.my_groups || [])
  const vote = async (gid) => {
    if (voted) return
    setPicked(gid)
    const s = await post('vote', { q_index: q.i, gid })
    if (!s) setPicked(null)
  }
  return (
    <div className="play-main">
      <span className="tag" style={{ color: 'var(--yellow)' }}>🗳️ {t('vote_title')}</span>
      <h2 style={{ fontSize: 20, marginTop: 10 }}>{pick(q.text, lang)}</h2>
      <Countdown state={state} serverNow={serverNow} />
      {voted && <p className="badge-warn" style={{ padding: 8, marginTop: 10 }}>✅ {t('vote_done')}</p>}
      <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
        {(q.choices || []).map((c, i) => {
          const own = mineSet.has(c.gid)
          return (
            <button key={c.gid} className={`btn block vote-btn ${voted === c.gid ? 'on' : ''}`} disabled={own || !!voted}
              onClick={() => vote(c.gid)} style={{ background: OPTION_STYLES[i % 4].color, justifyContent: 'flex-start', textAlign: 'left' }}>
              <span style={{ fontSize: 24 }}>{OPTION_STYLES[i % 4].shape}</span>
              <span className="grow">{c.text}</span>
              {own && <span className="tag">{t('vote_yours')}</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function WriteInResult({ q, state, phase }) {
  const { t, tn } = useLang()
  const choices = q.choices || []
  const mineSet = new Set(state.my_groups || [])
  const won = state.my_laugh_won || 0
  const iWon = (q.choices || []).some((c) => c.win && mineSet.has(c.gid))
  useEffect(() => { if (iWon) burst() }, [iWon])
  return (
    <div className="play-main">
      <h1 style={{ color: 'var(--pink)', marginTop: 10 }}>🏆 {t('vote_title')}</h1>
      {won > 0 && <div className="pts center" style={{ color: 'var(--lime)', fontSize: 44, fontWeight: 900 }}>{tn('writein_won', { n: <CountUp value={won} /> })}</div>}
      {choices.length === 0 && <p>{t('writein_none')}</p>}
      <div style={{ display: 'grid', gap: 8 }}>
        {[...choices].sort((a, b) => b.votes - a.votes).map((c) => (
          <div key={c.gid} className={`panel ${c.win ? 'win-card' : ''}`} style={{ margin: 0, padding: 12 }}>
            <div className="row" style={{ flexWrap: 'nowrap' }}>
              <span className="grow" style={{ fontWeight: 800 }}>{c.win && '👑 '}{c.text}</span>
              <b>{c.votes} {t('votes')}</b>
            </div>
            {mineSet.has(c.gid) && <span className="tag" style={{ color: 'var(--yellow)' }}>{t('vote_yours')}</span>}
          </div>
        ))}
      </div>
      {phase === 'riff' && <p><b>🎤 {t('riff_time')}</b> — {t('riff_sub')}</p>}
      <Stats me={state.me} />
    </div>
  )
}

function Wager({ state, post }) {
  const { t, tn } = useLang()
  const w = state.wager || { pct: 0, bet: 0, bottom: false, base: state.me.total }
  return (
    <div className="play-main center">
      <div className="big-emoji">💰</div>
      <h1 style={{ color: 'var(--yellow)' }}>{t('wager_title')}</h1>
      <p>{t('wager_sub')}</p>
      {w.bottom && <p className="badge-warn" style={{ padding: 10, fontSize: 18 }}>🚀 {t('wager_bottom')}</p>}
      <Segmented className="wager-grid" columns={5} label={t('wager_title')} value={w.pct} onChange={(pct) => post('wager', { pct })}
        options={[0, 25, 50, 75, 100].map((p) => ({ value: p, label: `${p}%` }))} />
      <p style={{ fontSize: 24, fontWeight: 900 }}>{tn('wager_bet', { n: <Num value={w.bet} /> })}</p>
      <p className="muted">{t('total')}: {w.base}</p>
    </div>
  )
}

function AwardsList({ awards }) {
  const { t } = useLang()
  if (!awards || !awards.length) return null
  const icons = { champion: '🧠', funniest: '😂', confidently_wrong: '🤡', best_heckle: '🗯️' }
  return (
    <div className="panel" style={{ textAlign: 'left' }}>
      <h3>🏅 {t('awards_title')}</h3>
      {awards.map((a) => (
        <div key={a.key} className="team-row">
          <b>{icons[a.key]} {t(`award_${a.key}`)}</b>
          <div>{a.team?.emoji} {teamLabel(a.team, t)}</div>
          {a.text && <div className="muted">“{a.text}”</div>}
        </div>
      ))}
    </div>
  )
}

function AwardsPhone({ state }) {
  const { t } = useLang()
  return (
    <div className="play-main center">
      <div className="big-emoji">{state.phase === 'podium' ? '🏆' : '🏅'}</div>
      <h1 style={{ color: 'var(--yellow)' }}>{state.phase === 'podium' ? t('podium_title') : t('awards_title')}</h1>
      <p style={{ fontSize: 22 }}>{t('rank')} <b>#{state.me.rank}</b> {t('of')} {state.team_count}</p>
      <Stats me={state.me} />
      <AwardsList awards={state.awards} />
    </div>
  )
}

// Roast card turns this phone red; spotlight / style points get a full-screen moment.
function PhoneEffects({ state, serverNow }) {
  const { t } = useLang()
  const active = useActiveEffects(state.effects, serverNow)
  const roast = active.find((e) => e.kind === 'roast')
  const spot = active.find((e) => e.kind === 'spotlight')
  const style = active.find((e) => e.kind === 'style')
  if (roast) {
    return (
      <div className="fx-phone roast" role="alert">
        <div className="big-emoji">🔥</div>
        <h1>{t('roast_card')}</h1>
        <p style={{ fontSize: 20 }}>{t('roast_phone')}</p>
      </div>
    )
  }
  if (spot) {
    return (
      <div className="fx-phone spot" role="alert">
        <div className="big-emoji">🎤</div>
        <h1>{t('spotlight')}</h1>
        <p style={{ fontSize: 20 }}>{t('spotlight_phone')}</p>
      </div>
    )
  }
  if (style) return <div className="toast" style={{ background: 'var(--yellow)', color: '#111', bottom: 150 }}>✨ {t('style_points', { n: style.points })}</div>
  return null
}

// LAUGH (hold, ~4/s), GROAN (tap), HECKLE (text -> host queue).
function ActionBar({ code, device, onNote, onError }) {
  const { t } = useLang()
  const pendingL = useRef(0)
  const pendingG = useRef(0)
  const holdTimer = useRef(null)
  const [holding, setHolding] = useState(false)
  const [pops, setPops] = useState([])
  const [heckleOpen, setHeckleOpen] = useState(false)

  const pop = (emoji) => {
    const id = Math.random()
    setPops((p) => [...p.slice(-8), { id, emoji, x: Math.random() * 80 + 10 }])
    setTimeout(() => setPops((p) => p.filter((x) => x.id !== id)), 900)
  }

  // Flush reactions every 500 ms (server also caps at 4/s per phone).
  useEffect(() => {
    const id = setInterval(async () => {
      const l = Math.min(pendingL.current, 4)
      const g = Math.min(pendingG.current, 4)
      pendingL.current = 0
      pendingG.current = 0
      if (!l && !g) return
      try { await api(`/rooms/${code}/react`, { method: 'POST', body: { device_id: device, laughs: l, groans: g }, retries: 0 }) } catch { /* fine */ }
    }, 500)
    return () => clearInterval(id)
  }, [code, device])

  const startLaugh = (e) => {
    e.preventDefault()
    if (holdTimer.current) return
    setHolding(true)
    pendingL.current += 1
    pop('😂')
    holdTimer.current = setInterval(() => { pendingL.current += 1; pop('😂') }, 250)
    if (navigator.vibrate) navigator.vibrate(15)
  }
  const stopLaugh = () => {
    clearInterval(holdTimer.current)
    holdTimer.current = null
    setHolding(false)
  }
  useEffect(() => stopLaugh, [])

  return (
    <>
      <div className="action-bar">
        <div className="pops" aria-hidden>{pops.map((p) => <span key={p.id} style={{ left: `${p.x}%` }}>{p.emoji}</span>)}</div>
        <button className={`ab-btn laugh ${holding ? 'holding' : ''}`} onPointerDown={startLaugh} onPointerUp={stopLaugh}
          onPointerLeave={stopLaugh} onPointerCancel={stopLaugh} onContextMenu={(e) => e.preventDefault()}>
          😂 {t('laugh')}<small>{t('laugh_hold')}</small>
        </button>
        <button className="ab-btn groan" onClick={() => { pendingG.current += 1; pop('😩') }}>😩 {t('groan')}</button>
        <button className="ab-btn heckle" onClick={() => setHeckleOpen(true)}>🗯️ {t('heckle')}</button>
      </div>
      <HeckleSheet code={code} device={device} open={heckleOpen} onOpenChange={setHeckleOpen} onNote={onNote} onError={onError} />
    </>
  )
}

function HeckleSheet({ code, device, open, onOpenChange, onNote, onError }) {
  const { t } = useLang()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const idRef = useRef(newId())
  const send = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    try {
      await api(`/rooms/${code}/heckle`, { method: 'POST', body: { device_id: device, id: idRef.current, text } })
      onNote(t('heckle_sent'))
      setText('')
      idRef.current = newId()
      onOpenChange(false)
    } catch (err) {
      onError(t(errKey(err)))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={`🗯️ ${t('heckle_title')}`} description={t('house_rules')}>
      <form onSubmit={send}>
        <textarea className="input" rows={3} maxLength={100} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={t('heckle_ph')} aria-label={t('heckle_ph')} />
        <p className="hint">{t('chars_left', { n: 100 - text.length })}</p>
        <button type="submit" className="btn pink block" disabled={busy || !text.trim()} style={{ marginTop: 10 }}>{t('heckle_send')}</button>
      </form>
    </Sheet>
  )
}

function ViralPhone({ state, post, serverNow }) {
  const { t } = useLang()
  const v = state.viral || { cards: [] }
  const p = state.phase
  const [picked, setPicked] = useState(null)
  const voted = v.my_vote ?? picked
  const win = v.winner != null ? v.cards[v.winner] : null
  if (p === 'viral_vote') {
    return (
      <div className="play-main">
        <span className="tag" style={{ color: 'var(--pink)' }}>🔥 {t('viral_tag')}</span>
        <h2 style={{ fontSize: 22, marginTop: 10 }}>{t('viral_vote_title')}</h2>
        <Countdown state={{ ...state, question: { time_limit: 15 } }} serverNow={serverNow} />
        {voted != null && <p className="badge-warn" style={{ padding: 8 }}>✅ {t('viral_voted')}</p>}
        <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
          {v.cards.map((c, i) => (
            <button key={i} className={`btn block vote-btn ${voted === i ? 'on' : ''}`} disabled={voted != null}
              style={{ background: OPTION_STYLES[i].color, justifyContent: 'flex-start', textAlign: 'left', flexDirection: 'column', alignItems: 'flex-start' }}
              onClick={async () => { setPicked(i); if (!(await post('viral_vote', { idx: i }))) setPicked(null) }}>
              <span>{OPTION_STYLES[i].shape} {c.title}</span>
              <small style={{ fontWeight: 500, opacity: 0.9 }}>{c.text}</small>
            </button>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div className="play-main center">
      {win && (
        <div className="panel" style={{ textAlign: 'left' }}>
          <h3>🔥 {win.title}</h3>
          <p style={{ margin: 0 }}>{win.text}</p>
          <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>{t('credit')} {win.credit}</p>
        </div>
      )}
      {p === 'viral_riff' && <><h1>🎤 {t('viral_riff_title')}</h1><Countdown state={{ ...state, question: { time_limit: 60 } }} serverNow={serverNow} /><p>{t('riff_sub')}</p></>}
      {p === 'viral_rate' && (
        v.my_rating ? <h2 style={{ color: 'var(--lime)' }}>⭐ {v.my_rating} · {t('viral_rated')}</h2> : (
          <>
            <h1 style={{ color: 'var(--yellow)' }}>⭐ {t('viral_rate_title')}</h1>
            <Segmented className="stars-grid" columns={5} label={t('viral_rate_title')} value={null}
              onChange={(n) => post('viral_rate', { stars: n })}
              options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: '⭐'.repeat(1) + n, aria: `${n}` }))} />
          </>
        )
      )}
      {p === 'viral_result' && (
        <>
          <h2>{t('viral_result_title')}</h2>
          <div className="pts" style={{ color: 'var(--yellow)' }}>⭐ {v.rating != null ? <CountUp value={v.rating} /> : '–'}</div>
          <p className="muted">{t('viral_ratings', { n: v.rated || 0 })}</p>
        </>
      )}
    </div>
  )
}
