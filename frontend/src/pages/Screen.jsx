import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import QRCode from 'qrcode'
import { Countdown, LangToggle, LaughMeter, OPTION_STYLES, Reconnecting, teamLabel, useActiveEffects } from '../components'
import { pick, useLang } from '../i18n'
import { usePoll } from '../usePoll'
import { audioReady, playSfx, unlockAudio } from '../sound'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Marquee, Num, burst } from '../ui'

const SPRING = { type: 'spring', stiffness: 380, damping: 32, mass: 0.9 }

function useStageScale() {
  const calc = () => Math.min(window.innerWidth / 1920, window.innerHeight / 1080)
  const [s, setS] = useState(calc)
  useEffect(() => {
    const on = () => setS(calc())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return s
}

// Both languages on the TV: primary (toggle) big, the other one underneath.
function Bi({ k, vars }) {
  const { t, t2 } = useLang()
  return <>{t(k, vars)} <span className="sec">/ {t2(k, vars)}</span></>
}

function useQr(url) {
  const [qr, setQr] = useState('')
  useEffect(() => {
    QRCode.toDataURL(url, { margin: 0, width: 800, errorCorrectionLevel: 'M' }).then(setQr).catch(() => setQr(''))
  }, [url])
  return qr
}

const METER_PHASES = ['reveal', 'riff', 'scoreboard', 'awards', 'podium', 'viral_riff', 'viral_result']

export default function Screen() {
  const { code: raw } = useParams()
  const code = raw.toUpperCase()
  const { t } = useLang()
  const { state, offline, error, serverNow } = usePoll(code, 'screen')
  const scale = useStageScale()
  const [audioOn, setAudioOn] = useState(audioReady())
  const played = useRef(new Set())
  const firstLoad = useRef(true)

  // Play each sound-board effect exactly once (skip ones that were already old on first load).
  useEffect(() => {
    if (!state?.effects) return
    const now = serverNow()
    for (const e of state.effects) {
      if (e.kind !== 'sfx' || played.current.has(e.id)) continue
      played.current.add(e.id)
      if (firstLoad.current && now - e.at > 1500) continue
      if (now - e.at < 4000) playSfx(e.name)
    }
    firstLoad.current = false
  }, [state, serverNow])

  const active = useActiveEffects(state?.effects, serverNow)
  const roast = active.find((e) => e.kind === 'roast')
  const showMeter = state && (METER_PHASES.includes(state.phase) || active.some((e) => ['heckle', 'spotlight', 'roast'].includes(e.kind)))

  let content
  if (error === 'room_not_found') content = <div className="screen-center">🤷 {t('err_room_not_found')}</div>
  else if (!state) content = <div className="screen-center">{t('loading')}</div>
  else if (state.phase === 'lobby') content = <Lobby state={state} code={code} />
  else if (state.phase === 'question_open' && state.question?.type === 'writein') content = <WriteInOpen state={state} serverNow={serverNow} />
  else if (state.phase === 'question_open') content = <QuestionView state={state} serverNow={serverNow} />
  else if (state.phase === 'question_locked') content = <Locked state={state} />
  else if (state.phase === 'vote') content = <VoteView state={state} serverNow={serverNow} />
  else if (['reveal', 'riff'].includes(state.phase) && state.question?.type === 'writein') content = <VoteView state={state} serverNow={serverNow} revealed />
  else if (state.phase === 'reveal' || state.phase === 'riff') content = <QuestionView state={state} serverNow={serverNow} revealed />
  else if (state.phase === 'scoreboard') content = <Board state={state} />
  else if (state.phase === 'wager') content = <WagerView state={state} />
  else if (state.phase === 'awards') content = <AwardsView state={state} />
  else if (state.phase === 'podium') content = <Podium state={state} />
  else if (state.phase === 'ended') content = <Ended state={state} code={code} />
  else if (state.phase.startsWith('viral_')) content = <ViralView state={state} serverNow={serverNow} />

  return (
    <div className="screen-wrap" onDoubleClick={() => document.documentElement.requestFullscreen?.().catch(() => {})}>
      <Reconnecting show={offline} />
      <div className={`stage ${roast ? 'shake' : ''} ${showMeter ? 'with-meter' : ''}`} style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
        <div className="stage-top">
          <span className="brand">🎤 Heckle & Hint</span>
          {state?.phase.startsWith('viral_') && <span style={{ fontSize: 56, fontWeight: 900, color: 'var(--pink)' }}>🔥 VIRAL DROP</span>}
          {state && state.q_index >= 0 && ['question_open', 'question_locked', 'vote', 'reveal', 'riff', 'scoreboard'].includes(state.phase) && (
            <span className="muted" style={{ fontSize: 56, fontWeight: 800 }}>
              {state.question?.final ? <Bi k="final_tag" />
                : state.question?.type === 'poll' ? <Bi k="poll_tag" />
                  : state.question?.type === 'writein' ? <Bi k="writein_tag" />
                    : <Bi k="question_x_of_y" vars={{ x: state.q_index + 1, y: state.q_total }} />}
            </span>
          )}
          <span className="code-pill">{code}</span>
        </div>
        {content}
        {showMeter && <LaughMeter reactLog={state.react_log} serverNow={serverNow} teamCount={state.team_count} />}
        {state && <StageEffects active={active} />}
      </div>
      {!audioOn && (
        <div className="tap-gate" onClick={async () => setAudioOn(await unlockAudio())}>
          <button className="tap-to-start">
            🔊 {t('tap_to_start')}<small>{t('tap_to_start_sub')}</small>
          </button>
        </div>
      )}
      <LangToggle />
    </div>
  )
}

function StageEffects({ active }) {
  const { t } = useLang()
  const heckle = active.find((e) => e.kind === 'heckle')
  const spot = active.find((e) => e.kind === 'spotlight')
  const roast = active.find((e) => e.kind === 'roast')
  const styles = active.filter((e) => e.kind === 'style')
  return (
    <>
      {heckle && (
        <div className="fx-heckle" key={heckle.id}>
          <div className="fx-tag">🗯️ <Bi k="heckle_on_screen" /></div>
          <div className="fx-heckle-text">{heckle.text ? `“${heckle.text}”` : '📵'}</div>
          <div className="fx-by">— {heckle.team?.emoji} {teamLabel(heckle.team, t)}</div>
        </div>
      )}
      {spot && (
        <div className="fx-spot" key={spot.id}>
          <div className="fx-tag">🎤 <Bi k="spotlight" /></div>
          <div className="fx-spot-name">{spot.team?.emoji} {teamLabel(spot.team, t)}</div>
        </div>
      )}
      {roast && (
        <div className="fx-roast" key={roast.id}>
          🔥 <Bi k="roast_card" /> 🔥
          <div className="fx-spot-name">{roast.team?.emoji} {teamLabel(roast.team, t)}</div>
        </div>
      )}
      <div className="fx-style-stack">
        {styles.map((e) => (
          <div className="fx-style" key={e.id}>✨ {e.team?.emoji} {teamLabel(e.team, t)} <b>+{e.points}</b></div>
        ))}
      </div>
    </>
  )
}

function Lobby({ state, code }) {
  const { t, t2 } = useLang()
  const joinUrl = `${window.location.origin}/join/${code}`
  const qr = useQr(joinUrl)
  // Fit up to 30 teams on one 16:9 screen: more teams -> more columns, smaller tiles.
  const n = state.teams.length
  const layout = n <= 5 ? { cols: 1, size: 56 } : n <= 10 ? { cols: 2, size: 48 } : n <= 18 ? { cols: 3, size: 40 } : { cols: 3, size: 30 }
  return (
    <div className="lobby-grid">
      <div>
        <div className="qr-box">{qr && <img src={qr} alt={joinUrl} />}</div>
        <p style={{ fontWeight: 900, margin: '24px 0 0', color: 'var(--yellow)' }}>{t('scan_to_join')}</p>
        <p className="sec" style={{ margin: 0 }}>{t2('scan_to_join')}</p>
        <p style={{ fontSize: 40, margin: '16px 0 0' }} className="muted">
          {t('or_visit')} <b style={{ color: 'var(--text)' }}>{window.location.host}</b>
        </p>
      </div>
      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <h2 style={{ fontSize: 72, fontWeight: 900, color: 'var(--pink)' }}>
          {state.teams.length ? <Bi k="teams_in" vars={{ n: state.teams.length }} /> : <Bi k="waiting_teams" />}
        </h2>
        <div className="tiles" style={{ gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))`, fontSize: layout.size }}>
          <AnimatePresence initial={false}>
            {state.teams.map((tm) => (
              <motion.div className="tile" key={tm.id} layout
                initial={{ opacity: 0, y: 28, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.15 } }} transition={SPRING}
                style={{ padding: `${Math.round(layout.size * 0.15)}px ${Math.round(layout.size * 0.4)}px` }}>
                {tm.emoji} {teamLabel(tm, t)}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
        <FactTicker teams={state.teams} />
      </div>
    </div>
  )
}

function FactTicker({ teams }) {
  const facts = teams.filter((x) => x.fact)
  return <Marquee items={facts.map((f) => `${f.emoji} “${f.fact}”`)} />
}

function QText({ q, size = 72 }) {
  const { lang, other } = useLang()
  return (
    <div className="screen-q" style={{ fontSize: size }}>
      {pick(q.text, lang)}
      {pick(q.text, other) !== pick(q.text, lang) && <span className="sec">{pick(q.text, other)}</span>}
    </div>
  )
}

function QuestionView({ state, serverNow, revealed = false }) {
  const { lang, other, t } = useLang()
  const q = state.question
  if (!q) return null
  const total = revealed ? Math.max(1, q.counts.reduce((a, b) => a + b, 0)) : 1
  const isPoll = q.type === 'poll'
  const maxCount = revealed ? Math.max(...q.counts) : 0
  return (
    <>
      <QText q={q} />
      <div className="screen-opts">
        {q.options.map((o, i) => {
          const win = revealed && (isPoll ? q.counts[i] === maxCount && maxCount > 0 : i === q.correct)
          const dim = revealed && !win
          return (
            <div key={i} className={`screen-opt ${win ? 'win' : ''} ${dim ? 'dim' : ''}`} style={{ background: OPTION_STYLES[i].color }}>
              {revealed && <div className="bar" style={{ width: `${(q.counts[i] / total) * 100}%` }} />}
              <span className="shape" style={{ zIndex: 1 }}>{OPTION_STYLES[i].shape}</span>
              <span className="txt">{pick(o, lang)}{pick(o, other) !== pick(o, lang) && <span className="sec">{pick(o, other)}</span>}</span>
              {revealed && <span className="num">{win && !isPoll ? '✓ ' : ''}<CountUpTV value={q.counts[i]} /></span>}
            </div>
          )
        })}
      </div>
      <div className="screen-meta" style={{ marginTop: 24 }}>
        {revealed ? (
          state.phase === 'riff'
            ? <span className="riff-banner">🎤 <Bi k="riff_time" /></span>
            : <span style={{ fontWeight: 900, color: 'var(--lime)' }}>💡 {isPoll ? t('poll_done') : pick(q.options[q.correct], lang)}</span>
        ) : (
          <Countdown state={state} serverNow={serverNow} big />
        )}
        <span style={{ fontWeight: 800 }}><Num value={state.answered_count} />/{state.team_count} <Bi k="answered" /></span>
      </div>
      {revealed && q.source && <div className="tv-source">📰 {q.source.title} · {hostOf(q.source.url)}</div>}
    </>
  )
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return '' }
}

// Viral Drop on the TV: vote (3 cards) -> riff (winner, big) -> rate -> result.
function ViralView({ state, serverNow }) {
  const v = state.viral || { cards: [] }
  const p = state.phase
  const win = v.winner != null ? v.cards[v.winner] : null
  if (p === 'viral_vote') {
    return (
      <>
        <div className="screen-q" style={{ fontSize: 64 }}><Bi k="viral_vote_title" /></div>
        <div className="viral-cards">
          {v.cards.map((c, i) => (
            <motion.div key={i} className="viral-card" style={{ borderTopColor: OPTION_STYLES[i].color }}
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ ...SPRING, delay: 0.12 * i }}>
              <div className="vc-shape" style={{ background: OPTION_STYLES[i].color }}>{OPTION_STYLES[i].shape}</div>
              <div className="vc-title">{c.title}</div>
              <div className="vc-text">{c.text}</div>
              <div className="vc-credit">via {c.credit}</div>
            </motion.div>
          ))}
        </div>
        <div className="screen-meta" style={{ marginTop: 20 }}>
          <Countdown state={{ ...state, question: { time_limit: 15 } }} serverNow={serverNow} big />
          <span style={{ fontWeight: 800 }}>🗳️ <Num value={state.answered_count} />/{state.team_count}</span>
        </div>
      </>
    )
  }
  return (
    <>
      {win && (
        <motion.div className="viral-winner" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={SPRING}>
          <div className="vc-title">{win.title}</div>
          <div className="vc-text">{win.text}</div>
          <div className="vc-credit">via {win.credit}</div>
        </motion.div>
      )}
      {p === 'viral_riff' && (
        <div className="screen-meta" style={{ marginTop: 24 }}>
          <span className="riff-banner">🎤 <Bi k="viral_riff_title" /></span>
          <Countdown state={{ ...state, question: { time_limit: 60 } }} serverNow={serverNow} big />
        </div>
      )}
      {p === 'viral_rate' && (
        <div className="screen-center" style={{ flex: 'none', marginTop: 30 }}>
          <div style={{ fontSize: 110, fontWeight: 900, color: 'var(--yellow)' }}>⭐ <Bi k="viral_rate_title" /></div>
          <div style={{ fontWeight: 800 }}><Num value={state.answered_count} />/{state.team_count}</div>
        </div>
      )}
      {p === 'viral_result' && (
        <div className="screen-center" style={{ flex: 'none', marginTop: 30 }}>
          <div style={{ fontWeight: 900, color: 'var(--pink)' }}><Bi k="viral_result_title" /></div>
          <div className="viral-stars">⭐ {v.rating != null ? <CountUpTV value={v.rating} /> : '–'}<span className="sec"> / 5</span></div>
          <div><Bi k="viral_ratings" vars={{ n: v.rated || 0 }} /></div>
        </div>
      )}
    </>
  )
}

function WriteInOpen({ state, serverNow }) {
  return (
    <>
      <QText q={state.question} size={80} />
      <div className="screen-center"><div className="lock-icon">✍️</div></div>
      <div className="screen-meta">
        <Countdown state={state} serverNow={serverNow} big />
        <span style={{ fontWeight: 800 }}><Num value={state.answered_count} />/{state.team_count} <Bi k="answered" /></span>
      </div>
    </>
  )
}

function Locked({ state }) {
  const q = state.question
  const wi = q?.type === 'writein'
  return (
    <div className="screen-center">
      {q && <QText q={q} size={64} />}
      <div className="lock-icon">{wi ? '🧐' : '🔒'}</div>
      <div style={{ fontWeight: 900, fontSize: 80, color: 'var(--yellow)' }}><Bi k="locked_title" /></div>
      <div><Bi k={wi ? 'writein_locked_screen' : 'locked_sub'} /></div>
      <div style={{ marginTop: 20, fontWeight: 800 }}>{state.answered_count}/{state.team_count} <Bi k="answered" /></div>
    </div>
  )
}

function VoteView({ state, serverNow, revealed = false }) {
  const q = state.question
  const choices = q.choices || []
  const top = Math.max(1, ...choices.map((c) => c.votes || 0))
  return (
    <>
      <QText q={q} size={60} />
      {choices.length === 0 ? (
        <div className="screen-center"><Bi k="writein_none" /></div>
      ) : (
        <div className="screen-votes" style={{ gridTemplateColumns: choices.length > 3 ? '1fr 1fr' : '1fr' }}>
          {choices.map((c, i) => (
            <div key={c.gid} className={`screen-opt vote ${revealed && c.win ? 'win' : ''} ${revealed && !c.win ? 'dim' : ''}`}
              style={{ background: OPTION_STYLES[i % 4].color }}>
              {revealed && <div className="bar" style={{ width: `${((c.votes || 0) / top) * 100}%` }} />}
              <span className="shape" style={{ zIndex: 1 }}>{OPTION_STYLES[i % 4].shape}</span>
              <span className="txt">{c.text || '📵'}</span>
              {revealed && <span className="num">{c.win ? '👑 ' : ''}<CountUpTV value={c.votes} /></span>}
            </div>
          ))}
        </div>
      )}
      <div className="screen-meta" style={{ marginTop: 20 }}>
        {revealed
          ? (state.phase === 'riff' ? <span className="riff-banner">🎤 <Bi k="riff_time" /></span> : <span style={{ fontWeight: 900, color: 'var(--lime)' }}>🏆 <Bi k="vote_title" /></span>)
          : <><Countdown state={state} serverNow={serverNow} big /><span style={{ fontWeight: 800 }}>🗳️ {state.answered_count}/{state.voters_count}</span></>}
      </div>
    </>
  )
}

// Rows are rendered in rank order; motion's layout animation springs them to their new place.
function Board({ state }) {
  const { t } = useLang()
  return (
    <>
      <h2 style={{ fontSize: 88, fontWeight: 900, color: 'var(--pink)', marginTop: 16 }}><Bi k="top5" /></h2>
      <div className="board">
        {state.top.map((tm, i) => (
          <motion.div className={`board-row ${i === 0 ? 'lead' : ''}`} key={tm.id} layout transition={SPRING}
            initial={{ opacity: 0, x: -40 }} animate={{ opacity: 1, x: 0, transition: { ...SPRING, delay: 0.06 * i } }}>
            <span className="pos">#{tm.rank}</span>
            <span className="nm">{tm.emoji} {teamLabel(tm, t)}</span>
            <span className="split">🧠 <Num value={tm.brain} /> · 😂 <Num value={tm.laugh} /></span>
            <span className="sc"><Num value={tm.total} /></span>
          </motion.div>
        ))}
      </div>
    </>
  )
}

// Numbers on the TV roll up from 0 when they first appear.
function CountUpTV({ value }) {
  const [v, setV] = useState(0)
  useEffect(() => { const id = setTimeout(() => setV(value), 150); return () => clearTimeout(id) }, [value])
  return <Num value={v} />
}

function WagerView({ state }) {
  const { t } = useLang()
  const w = state.wager || { bottom: [], placed: 0 }
  return (
    <div className="screen-center">
      <div className="lock-icon">💰</div>
      <div style={{ fontWeight: 900, fontSize: 110, color: 'var(--yellow)' }}><Bi k="wager_screen" /></div>
      <div><Bi k="wager_sub" /></div>
      {w.bottom.length > 0 && (
        <div style={{ marginTop: 30 }}>
          <div style={{ color: 'var(--pink)', fontWeight: 900 }}>🚀 <Bi k="wager_double" /></div>
          <div className="row" style={{ justifyContent: 'center', gap: 24, marginTop: 12 }}>
            {w.bottom.map((tm) => tm && <span className="tile" key={tm.id}>{tm.emoji} {teamLabel(tm, t)}</span>)}
          </div>
        </div>
      )}
      <div style={{ marginTop: 30, fontWeight: 800 }}><Bi k="wager_placed" vars={{ n: w.placed }} /></div>
    </div>
  )
}

const AWARD_ICONS = { champion: '🧠', funniest: '😂', confidently_wrong: '🤡', best_heckle: '🗯️' }

function AwardsView({ state }) {
  const { t } = useLang()
  const awards = state.awards || []
  return (
    <>
      <h2 style={{ fontSize: 96, fontWeight: 900, color: 'var(--yellow)', marginTop: 10 }}>🏅 <Bi k="awards_title" /></h2>
      <div className="awards-grid">
        {awards.map((a, i) => (
          <motion.div className="award-card" key={a.key} initial={{ opacity: 0, y: 30, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ ...SPRING, delay: 0.25 + i * 0.9 }}>
            <div className="award-icon">{AWARD_ICONS[a.key]}</div>
            <div className="award-name"><Bi k={`award_${a.key}`} /></div>
            <div className="award-team">{a.team?.emoji} {teamLabel(a.team, t)}</div>
            {a.key === 'best_heckle' && <div className="award-text">{a.text ? `“${a.text}”` : '📵'}</div>}
          </motion.div>
        ))}
      </div>
    </>
  )
}

function Podium({ state }) {
  const { t } = useLang()
  const [a, b, c] = state.top
  const reduce = useReducedMotion()
  useEffect(() => { const id = setTimeout(() => burst('big'), 1900); return () => clearTimeout(id) }, [])
  const col = (tm, place, h, color) => tm && (
    <motion.div className="pod-col" initial={{ opacity: 0, y: reduce ? 0 : 120 }} animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: (3 - place) * 0.6 }}>
      <div className="pod-emoji">{tm.emoji}</div>
      <div className="pod-name">{teamLabel(tm, t)}</div>
      <div className="pod-score"><CountUpTV value={tm.total} /></div>
      <div className="pod-block" style={{ height: h, background: color }}>{place}</div>
    </motion.div>
  )
  return (
    <>
      <h2 style={{ fontSize: 96, fontWeight: 900, color: 'var(--pink)', marginTop: 10 }}>🏆 <Bi k="podium_title" /></h2>
      <div className="podium-row">
        {col(b, 2, 300, '#C0C0D0')}
        {col(a, 1, 420, 'var(--yellow)')}
        {col(c, 3, 220, '#CD7F32')}
      </div>
    </>
  )
}

function Ended({ state, code }) {
  const qr = useQr(`${window.location.origin}/recap/${code}`)
  const p = state.profile || {}
  const handles = [['💬', 'Zalo', p.zalo], ['📘', 'Facebook', p.facebook], ['📸', 'Instagram', p.instagram], ['🎵', 'TikTok', p.tiktok]].filter((x) => x[2])
  return (
    <div className="lobby-grid" style={{ gridTemplateColumns: '1fr 560px' }}>
      <div>
        <h2 style={{ fontSize: 110, fontWeight: 900, color: 'var(--pink)' }}>🎉 <Bi k="thanks_title" /></h2>
        <div style={{ fontWeight: 900, color: 'var(--yellow)', marginTop: 20 }}><Bi k="follow_title" /></div>
        {p.host_name && <div style={{ fontSize: 80, fontWeight: 900 }}>🎤 {p.host_name}</div>}
        {handles.map(([icon, label, v]) => <div key={label}>{icon} {label}: <b>{v}</b></div>)}
      </div>
      <div>
        <div className="qr-box" style={{ width: 520 }}>{qr && <img src={qr} alt="recap" />}</div>
        <p style={{ fontWeight: 900, color: 'var(--yellow)', marginTop: 20 }}><Bi k="recap_scan" /></p>
      </div>
    </div>
  )
}
