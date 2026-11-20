import { useCallback, useEffect, useMemo, useState } from 'react'
import { Tabs } from '@base-ui/react/tabs'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errKey, hostKey } from '../api'
import { Countdown, LangToggle, LaughMeter, OPTION_STYLES, Reconnecting, newId } from '../components'
import { Num, SwitchRow, clsx, toast } from '../ui'
import {
  AwardsPanel, CommandMenu, HeckleQueue, ProfilePanel, RiffFuel, SoundBoard, StarSheet, TeamChip, TeamSheet, WagerPanel, WriteInPanel,
} from './HostPanels'
import QuestionEditor from './QuestionEditor'
import { LiveContentPanel, ViralHostPanel } from './LivePanels'
import { pick, useLang } from '../i18n'
import { usePoll } from '../usePoll'

function nextLabel(s, t) {
  switch (s.phase) {
    case 'lobby': return t('next_start')
    case 'question_open': return t('next_lock')
    case 'question_locked': {
      if (s.question?.type === 'writein') {
        const n = (s.writeins || []).filter((g) => g.approved && !g.hidden).length
        return n ? t('next_vote', { n }) : t('next_reveal')
      }
      return t('next_reveal')
    }
    case 'vote': return t('next_reveal_votes')
    case 'reveal': return t('next_riff')
    case 'riff': return t('next_scoreboard')
    case 'scoreboard':
      if (!s.next_question) return t('next_awards')
      if (s.next_question.final) return t('next_wager')
      return t('next_question', { x: s.q_index + 2, y: s.q_total })
    case 'wager': return t('next_final')
    case 'awards': return t('next_podium')
    case 'podium': return t('next_follow')
    case 'viral_vote': return t('next_viral_riff')
    case 'viral_riff': return t('next_viral_rate')
    case 'viral_rate': return t('next_viral_result')
    case 'viral_result': return t('next_viral_back')
    default: return t('next_restart')
  }
}

export default function Host() {
  const { code: raw } = useParams()
  const code = raw.toUpperCase()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { t } = useLang()

  // Save ?key=… to localStorage, then drop it from the address bar.
  const urlKey = params.get('key')
  if (urlKey) hostKey.set(code, urlKey)
  const key = urlKey || hostKey.get(code)
  useEffect(() => { if (urlKey) nav(`/host/${code}`, { replace: true }) }, [urlKey, code, nav])

  const { state, setState, offline, error, serverNow, refresh } = usePoll(code, 'host', { hostKey: key, enabled: !!key })
  const [confirmReset, setConfirmReset] = useState(false)
  const [busy, setBusy] = useState(false)
  const [starOpen, setStarOpen] = useState(false)
  const [cmdOpen, setCmdOpen] = useState(false)
  const [teamId, setTeamId] = useState(null) // team whose action drawer is open
  const [tab, setTab] = useState('live')

  useEffect(() => {
    if (!confirmReset) return
    const id = setTimeout(() => setConfirmReset(false), 3000)
    return () => clearTimeout(id)
  }, [confirmReset])
  // ⌘K / Ctrl+K opens quick actions on a laptop.
  useEffect(() => {
    const on = (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setCmdOpen((o) => !o) } }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [])

  const act = useCallback(async (action, data = {}, withExpect = false) => {
    if (withExpect && state) Object.assign(data, { expect_phase: state.phase, expect_q: state.q_index })
    setBusy(true)
    try {
      const s = await api(`/rooms/${code}/host/${action}`, { method: 'POST', body: data, key })
      setState(s)
      return s
    } catch (e) {
      toast.error(t(errKey(e)))
      refresh()
      return null
    } finally {
      setBusy(false)
    }
  }, [state, code, key, setState, refresh, t])

  if (!key || error === 'not_host') {
    return (
      <div className="page center">
        <div className="big-emoji">🔑</div>
        <h2>{t('host_key_missing_title')}</h2>
        <p>{t('host_key_missing')}</p>
        <Link className="btn yellow" to="/">{t('go_home')}</Link>
      </div>
    )
  }
  if (error === 'room_not_found') {
    return <div className="page center"><div className="big-emoji">🤷</div><p>{t('err_room_not_found')}</p>
      <Link className="btn yellow" to="/">{t('go_home')}</Link></div>
  }
  if (!state) return <div className="page center muted">{t('loading')}</div>

  const s = state
  const q = s.question
  const revealed = ['reveal', 'riff', 'scoreboard'].includes(s.phase)
  const onNext = () => (s.phase === 'ended' ? act('reset') : act('next', {}, true))
  // +200 Style Points, with Undo right inside the Sonner toast.
  const onStyle = async (tm) => {
    const r = await act('style', { team_id: tm.id, action_id: newId() })
    if (r?.created) {
      toast.success(t('style_given', { team: tm.name }), {
        duration: 6000,
        action: { label: `↩ ${t('undo')}`, onClick: () => act('undo', { entry_id: r.created }) },
      })
    }
  }
  const timed = ['question_open', 'vote', 'viral_vote', 'viral_riff', 'viral_rate'].includes(s.phase)
  const viral = s.phase.startsWith('viral_')
  const pendingHeckles = (s.heckles || []).filter((h) => h.status === 'pending').length
  const pendingMod = s.teams.filter((x) => x.name_status === 'pending' || ['pending', 'flagged'].includes(x.fact_status)).length
  const openTeam = (tm) => setTeamId(tm.id)
  const team = s.teams.find((x) => x.id === teamId)

  return (
    <div>
      <Reconnecting show={offline} />
      <div className="topbar">
        <span className="brand">🎤 {t('host_console')}</span>
        <span className="code-pill">{code}</span>
        <button className="icon-btn" onClick={() => setCmdOpen(true)} aria-label={t('quick_actions')} title={`${t('quick_actions')} (⌘K)`}>⌕</button>
        <LangToggle />
      </div>
      <Tabs.Root value={tab} onValueChange={setTab} className="host-tabs">
        <Tabs.List className="tabs-list">
          <Tabs.Tab value="live" className="tab">🎤 {t('tab_live')}{pendingHeckles > 0 && <span className="tab-badge">{pendingHeckles}</span>}</Tabs.Tab>
          <Tabs.Tab value="teams" className="tab">👥 {t('tab_teams')}<span className="tab-count">{s.team_count}</span>{pendingMod > 0 && <span className="tab-badge">{pendingMod}</span>}</Tabs.Tab>
          <Tabs.Tab value="setup" className="tab">⚙️ {t('tab_setup')}</Tabs.Tab>
          <Tabs.Indicator className="tabs-indicator" />
        </Tabs.List>

        <Tabs.Panel value="live" className="page tab-panel">
          <div className="house-rules">🛡️ {t('house_rules')}<br /><span className="muted" style={{ fontWeight: 500 }}>{t('house_rules_2')}</span></div>
          {viral ? <ViralHostPanel s={s} serverNow={serverNow} /> : <Teleprompter s={s} q={q} revealed={revealed} serverNow={serverNow} />}
          {s.phase === 'lobby' && <DemoPanel s={s} act={act} busy={busy} />}
          {q && q.type !== 'writein' && <RiffFuel s={s} q={q} />}
          {q && q.type !== 'writein' && <RiffRadar s={s} q={q} act={act} onOpen={openTeam} />}
          {q && q.type === 'writein' && <WriteInPanel s={s} act={act} />}
          {s.phase === 'wager' && <WagerPanel s={s} />}
          {['lobby', 'scoreboard'].includes(s.phase) && <LiveContentPanel s={s} code={code} hostKey={key} act={act} setState={setState} />}
          <AwardsPanel s={s} />
          <div className="panel">
            <div className="ctl-grid">
              {s.phase !== 'lobby' && <button className="btn small" onClick={() => act('back', {}, true)} disabled={busy}>◀ {t('btn_back')}</button>}
              {timed && <button className="btn small" onClick={() => act('add_time')} disabled={busy}>⏱ {t('btn_plus10')}</button>}
              {timed && (
                <button className={clsx('btn small', s.frozen && 'yellow')} onClick={() => act('freeze', { frozen: !s.frozen })} disabled={busy}>
                  {s.frozen ? `▶ ${t('btn_unfreeze')}` : `⏸ ${t('btn_freeze')}`}
                </button>
              )}
              {(viral || ['question_open', 'question_locked', 'vote', 'reveal', 'riff', 'scoreboard'].includes(s.phase)) && (
                <button className="btn small" onClick={() => act('skip', {}, true)} disabled={busy}>⏭ {t('btn_skip')}</button>
              )}
              <button className={clsx('btn small', confirmReset && 'red')} style={{ gridColumn: 'span 2' }} disabled={busy}
                onClick={() => { if (confirmReset) { setConfirmReset(false); act('reset') } else setConfirmReset(true) }}>
                ↺ {confirmReset ? t('btn_reset_confirm') : t('btn_reset')}
              </button>
            </div>
          </div>
          <HeckleQueue s={s} act={act} serverNow={serverNow} />
          <SoundBoard s={s} act={act} />
        </Tabs.Panel>

        <Tabs.Panel value="teams" className="page tab-panel">
          <TeamsPanel s={s} act={act} onOpen={openTeam} />
          <DemoPanel s={s} act={act} busy={busy} />
        </Tabs.Panel>

        <Tabs.Panel value="setup" className="page tab-panel">
          {s.db_mode === 'memory' && <p className="hint">ℹ️ {t('db_memory')}</p>}
          <ScreenPanel s={s} code={code} act={act} />
          {!['lobby', 'scoreboard'].includes(s.phase) && <LiveContentPanel s={s} code={code} hostKey={key} act={act} setState={setState} />}
          <ProfilePanel s={s} act={act} />
          <QuestionEditor code={code} hostKey={key} onToast={(m) => toast.error(m)} version={s.q_index} />
          <div className="row" style={{ marginTop: 10 }}>
            <Link className="btn small ghost" to={`/host/${code}/report`}>📋 {t('set_report')}</Link>
            <Link className="btn small ghost" to={`/recap/${code}`} target="_blank">🏆 {t('public_recap')}</Link>
          </div>
        </Tabs.Panel>
      </Tabs.Root>

      <div className="sticky-cta"><div className="inner">
        <div className="row" style={{ flexWrap: 'nowrap', gap: 8 }}>
          <button className="btn yellow star-btn" onClick={() => setStarOpen(true)} aria-label={t('star_title')}>⭐</button>
          <button className="next-btn" onClick={onNext} disabled={busy}>{nextLabel(s, t)}</button>
        </div>
      </div></div>
      <StarSheet act={act} open={starOpen} onOpenChange={setStarOpen} onSaved={() => toast.success(t('star_saved'))} />
      <TeamSheet tm={team} open={!!team} onOpenChange={(o) => { if (!o) setTeamId(null) }} act={act} onStyle={onStyle} />
      <CommandMenu s={s} open={cmdOpen} onOpenChange={setCmdOpen} act={act} onOpenTeam={(tm) => { setCmdOpen(false); setTimeout(() => openTeam(tm), 250) }}
        onNext={onNext} nextText={nextLabel(s, t)} onStar={() => { setCmdOpen(false); setTimeout(() => setStarOpen(true), 250) }} />
    </div>
  )
}

function Teleprompter({ s, q, revealed, serverNow }) {
  const { t, lang } = useLang()
  if (!q) {
    return (
      <div className="panel prompter">
        <h3>{t('teleprompter')} · {t(`phase_${s.phase}`)}</h3>
        {s.next_question ? (
          <>
            <p className="muted" style={{ margin: 0 }}>{t('next_up')}: {s.next_question.type === 'poll' ? t('poll_tag') : `Q${s.next_question.i + 1}`}</p>
            <div className="q">{pick(s.next_question.text, lang)}</div>
          </>
        ) : <div className="q">🎉 {t('night_over')}</div>}
        <p className="muted">{t('answered_x', { x: 0, y: s.team_count })}</p>
      </div>
    )
  }
  return (
    <div className="panel prompter">
      <div className="row">
        <h3 className="grow" style={{ margin: 0 }}>
          {q.type === 'poll' ? t('poll_tag') : t('question_x_of_y', { x: q.i + 1, y: s.q_total })} · {t(`phase_${s.phase}`)}
        </h3>
        <b>{t('answered_x', { x: s.answered_count, y: s.team_count })}</b>
      </div>
      {['question_open', 'vote'].includes(s.phase) && <Countdown state={s} serverNow={serverNow} />}
      {['reveal', 'riff', 'scoreboard'].includes(s.phase) && (
        <div className="row host-meter">
          <LaughMeter reactLog={s.react_log} serverNow={serverNow} teamCount={s.team_count} compact />
          {s.active_bit && <span className="muted">🔴 {t('active_bit', { b: pick(s.active_bit, lang) })}</span>}
        </div>
      )}
      <div className="q">{pick(q.text, lang)}</div>
      {q.type === 'poll'
        ? <div className="ans" style={{ background: 'var(--pink)', color: '#fff' }}>🗳️ {t('poll_done')}</div>
        : q.type === 'writein' ? <div className="ans" style={{ background: 'var(--yellow)' }}>✍️ {t('writein_tag')}</div>
        : <div className="ans">✅ {t('answer_label')}: {OPTION_STYLES[q.correct].shape} {pick(q.options[q.correct], lang)}</div>}
      <p className="line"><small>{t('setup_label')}</small>{pick(q.setup, lang)}</p>
      <p className="line punch"><small>{t('punchline_label')}</small>
        {revealed ? pick(q.punchline, lang) : <span className="muted">🔒 {t('punchline_locked')}</span>}</p>
      {q.notes && <p className="line" style={{ borderColor: 'var(--line)' }}><small>{t('notes_label')}</small>{q.notes}</p>}
    </div>
  )
}

function RiffRadar({ s, q, act, onOpen }) {
  const { t, lang } = useLang()
  const teams = useMemo(() => Object.fromEntries(s.teams.map((x) => [x.id, x])), [s.teams])
  const showPicks = s.phase !== 'question_open'
  const byOpt = [[], [], [], []]
  for (const [tid, a] of Object.entries(s.answers || {})) if (teams[tid]) byOpt[a.choice].push({ ...teams[tid], ms: a.ms })
  byOpt.forEach((l) => l.sort((a, b) => a.ms - b.ms))
  const noAnswer = s.teams.filter((x) => !(s.answers || {})[x.id])
  return (
    <div className="panel">
      <h3>📡 {t('riff_radar')}</h3>
      {!showPicks && <p className="muted" style={{ margin: 0 }}>{t('radar_wait')}</p>}
      {showPicks && q.options.map((o, i) => (
        <div className="radar-opt" key={i}>
          <div className="head" style={{ background: OPTION_STYLES[i].color }}>
            <span>{OPTION_STYLES[i].shape}</span>
            <span>{pick(o, lang)}{q.type !== 'poll' && i === q.correct ? ' ✅' : ''}</span>
            <span className="cnt">{byOpt[i].length}</span>
          </div>
          <div className="teams">{byOpt[i].map((tm) => <TeamChip key={tm.id} tm={tm} act={act} onOpen={onOpen} />)}</div>
        </div>
      ))}
      {showPicks && noAnswer.length > 0 && (
        <div className="radar-opt">
          <div className="head" style={{ background: '#444' }}>😴 {t('no_answer_teams')}<span className="cnt">{noAnswer.length}</span></div>
          <div className="teams">{noAnswer.map((tm) => <TeamChip key={tm.id} tm={tm} act={act} onOpen={onOpen} />)}</div>
        </div>
      )}
    </div>
  )
}

function ScreenPanel({ s, code, act }) {
  const { t } = useLang()
  const joinUrl = `${window.location.origin}/join/${code}`
  const copy = async () => {
    try { await navigator.clipboard.writeText(joinUrl); toast.success(t('copied')) } catch { /* no clipboard */ }
  }
  return (
    <div className="panel">
      <h3>📺 {t('big_screen')}</h3>
      <div className="row">
        <a className="btn small yellow" href={`/screen/${code}`} target="_blank" rel="noreferrer">{t('open_screen')} ↗</a>
        <button className="btn small" onClick={copy}>🔗 {t('copy_link')}</button>
      </div>
      <div style={{ marginTop: 10 }}>
        <SwitchRow danger checked={s.blackout} onChange={(on) => act('blackout', { on })}
          label={`⬛ ${s.blackout ? t('blackout_on') : t('blackout')}`} hint={t('blackout_help')} />
      </div>
    </div>
  )
}

function TeamsPanel({ s, act, onOpen }) {
  const { t } = useLang()
  return (
    <div className="panel">
      <h3>👥 {t('teams_label')} ({s.team_count}/30)</h3>
      {s.teams.length === 0 && <p className="muted" style={{ margin: 0 }}>{t('no_teams_yet')}</p>}
      {s.teams.map((tm) => (
        <div className="team-row" key={tm.id}>
          <button className="team-row-main" onClick={() => onOpen(tm)} aria-label={`${t('team_actions')}: ${tm.name}`}>
            <span style={{ fontSize: 24 }}>{tm.emoji}</span>
            <span className="grow team-row-name">
              <b style={{ textDecoration: tm.name_hidden ? 'line-through' : 'none' }}>{tm.name}</b>
              <span className="team-row-meta">
                <span className={`roast-${tm.roast}`}>🌶️ {t(`roast_${tm.roast}`)}</span>
                {tm.mic && <span>🎤</span>}
                {tm.demo && <span className="muted">{t('demo_tag')}</span>}
                {tm.name_status === 'pending' && <span className="badge-warn">⚠ {t('status_flagged')}</span>}
                {tm.name_hidden && <span className="badge-hidden">{t('status_hidden')}</span>}
                {tm.fact && tm.fact_status !== 'approved' && !tm.fact_hidden && <span className="badge-warn">💬 {t('status_pending')}</span>}
              </span>
            </span>
            <b className="team-row-score"><Num value={tm.total} /></b>
            <span className="chev" aria-hidden>›</span>
          </button>
          {tm.name_status === 'pending' && (
            <button className="btn small lime" style={{ marginTop: 6 }} onClick={() => act('mod', { team_id: tm.id, field: 'name', op: 'approve' })}>✓ {t('btn_approve')}</button>
          )}
        </div>
      ))}
    </div>
  )
}

function DemoPanel({ s, act, busy }) {
  const { t } = useLang()
  return (
    <div className="panel">
      <h3>🧪 {t('demo_mode')}</h3>
      {s.demo_loaded
        ? <button className="btn small block" onClick={() => act('demo_clear')} disabled={busy}>🧹 {t('clear_demo')}</button>
        : <button className="btn yellow block" onClick={() => act('demo_load')} disabled={busy}>➕ {t('load_demo')}</button>}
      {s.demo_loaded && (
        <div style={{ marginTop: 10 }}>
          <SwitchRow checked={s.sim_on} onChange={(on) => act('demo_sim', { on })} label={t('simulate_crowd')} hint={t('sim_help')} />
        </div>
      )}
    </div>
  )
}
