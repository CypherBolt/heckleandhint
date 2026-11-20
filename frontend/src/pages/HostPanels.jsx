// Tier 2 host console panels: Riff Fuel, team actions, write-ins, heckle queue,
// sound board, wager/awards info, follow card settings and the star sheet.
import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { OPTION_STYLES, newId } from '../components'
import { pick, useLang } from '../i18n'
import { Num, Sheet, clsx, toast } from '../ui'

// Tap a team anywhere (Riff Radar, Teams tab, quick actions) -> this drawer.
export function TeamSheet({ tm, open, onOpenChange, act, onStyle }) {
  const { t } = useLang()
  const close = () => onOpenChange(false)
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={tm ? `${tm.emoji} ${tm.name}` : ''} tone="yellow">
      {tm && (
        <>
          <div className="row" style={{ gap: 8, marginBottom: 12 }}>
            <span className={`tag roast-${tm.roast}`}>🌶️ {t(`roast_${tm.roast}`)}</span>
            {tm.mic && <span className="tag" style={{ color: 'var(--lime)' }}>🎤 {t('mic_ready')}</span>}
            <span className="grow" />
            <b style={{ fontSize: 22 }}>🧠 <Num value={tm.brain} /> · 😂 <Num value={tm.laugh} /></b>
          </div>
          {tm.name_reason && <p className="mod-reason">⚠ {t('mod_reason')}: {tm.name_reason}</p>}
          <div className="action-grid">
            <button className="btn yellow" onClick={() => { onStyle(tm); close() }}>✨ {t('btn_style')}</button>
            {tm.roast !== 'off'
              ? <button className="btn red" onClick={() => { act('roast', { team_id: tm.id, action_id: newId() }); close() }}>🔥 {t('btn_roast')}</button>
              : <p className="action-note">🚫 {t('roast_is_off')}</p>}
            {tm.mic
              ? <button className="btn pink" onClick={() => { act('spotlight', { team_id: tm.id, action_id: newId() }); close() }}>🎤 {t('btn_spotlight')}</button>
              : <p className="action-note">🎤 {t('not_mic_ready')}</p>}
            <button className="btn" onClick={() => act('mod', { team_id: tm.id, field: 'name', op: tm.name_hidden ? 'show' : 'hide' })}>
              {tm.name_hidden ? `👁 ${t('btn_show')}` : `🙈 ${t('btn_hide')}`}
            </button>
            {tm.name_status === 'pending' && (
              <button className="btn lime" onClick={() => act('mod', { team_id: tm.id, field: 'name', op: 'approve' })}>✓ {t('btn_approve')}</button>
            )}
          </div>
          {tm.fact && (
            <div className="fact-box">
              <small>{t('fact_label')}</small>
              <p style={{ margin: '4px 0 8px', textDecoration: tm.fact_hidden ? 'line-through' : 'none' }}>“{tm.fact}”
                {tm.fact_status === 'flagged' && <span className="badge-warn"> ⚠ {t('status_flagged')}</span>}</p>
              {tm.fact_reason && <p className="mod-reason">⚠ {t('mod_reason')}: {tm.fact_reason}</p>}
              <div className="row">
                {tm.fact_status !== 'approved' && <button className="btn small lime" onClick={() => act('mod', { team_id: tm.id, field: 'fact', op: 'approve' })}>✓ {t('btn_approve')}</button>}
                <button className="btn small" onClick={() => act('mod', { team_id: tm.id, field: 'fact', op: tm.fact_hidden ? 'show' : 'hide' })}>
                  {tm.fact_hidden ? `👁 ${t('btn_show')}` : `🙈 ${t('btn_hide')}`}
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </Sheet>
  )
}

// Team chip used in the Riff Radar: tap to open the team's action drawer.
export function TeamChip({ tm, act, onOpen }) {
  const { t } = useLang()
  if (!tm) return null
  return (
    <span className="chip">
      <button className="chip-main" onClick={() => onOpen(tm)}>
        {tm.emoji} {tm.name_hidden ? <s>{tm.name}</s> : tm.name}
        <span className={`roast-${tm.roast}`} title={t('roast_level')}>🌶️{t(`roast_${tm.roast}`)}</span>
        {tm.mic && <span title={t('mic_ready')}>🎤</span>}
      </button>
      <button className="chip-btn" onClick={() => act('mod', { team_id: tm.id, field: 'name', op: tm.name_hidden ? 'show' : 'hide' })}
        aria-label={tm.name_hidden ? t('btn_show') : t('btn_hide')} title={tm.name_hidden ? t('btn_show') : t('btn_hide')}>
        {tm.name_hidden ? '👁' : '🙈'}
      </button>
    </span>
  )
}

// cmdk quick actions: one search box for teams, sounds, heckles and room controls.
export function CommandMenu({ s, open, onOpenChange, act, onOpenTeam, onNext, nextText, onStar }) {
  const { t } = useLang()
  const [q, setQ] = useState('')
  useEffect(() => { if (!open) setQ('') }, [open])
  const run = (fn) => () => { fn(); onOpenChange(false) }
  const icons = { rimshot: '🥁', trombone: '🎺', airhorn: '📯', drumroll: '🪘', ding: '🔔', buzz: '❌' }
  const pending = (s.heckles || []).filter((h) => h.status === 'pending').slice(0, 5)
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={`⌕ ${t('quick_actions')}`} tone="lime">
      <Command label={t('quick_actions')} className="cmdk" loop>
        <Command.Input value={q} onValueChange={setQ} placeholder={t('search_ph')} className="input cmdk-input" />
        <Command.List className="cmdk-list">
          <Command.Empty className="cmdk-empty">{t('cmd_empty')}</Command.Empty>
          <Command.Group heading={t('cmd_room')}>
            <Command.Item value={`next ${nextText}`} onSelect={run(onNext)}>▶ {nextText}</Command.Item>
            <Command.Item value={`star ${t('star_title')}`} onSelect={onStar}>⭐ {t('star_title')}</Command.Item>
            <Command.Item value={`blackout ${t('blackout')}`} onSelect={run(() => act('blackout', { on: !s.blackout }))}>
              ⬛ {s.blackout ? t('blackout_on') : t('blackout')}
            </Command.Item>
          </Command.Group>
          {pending.length > 0 && (
            <Command.Group heading={t('cmd_heckles')}>
              {pending.map((h) => (
                <Command.Item key={h.id} value={`heckle ${h.text}`} onSelect={run(() => act('heckle', { heckle_id: h.id, op: 'show' }))}>
                  📺 “{h.text}”
                </Command.Item>
              ))}
            </Command.Group>
          )}
          <Command.Group heading={t('cmd_teams')}>
            {s.teams.map((tm) => (
              <Command.Item key={tm.id} value={`team ${tm.name} ${tm.roast} ${tm.mic ? 'mic' : ''}`} onSelect={() => onOpenTeam(tm)}>
                <span>{tm.emoji} {tm.name}</span>
                <span className="cmdk-meta"><span className={`roast-${tm.roast}`}>🌶️</span>{tm.mic && '🎤'} <Num value={tm.total} /></span>
              </Command.Item>
            ))}
          </Command.Group>
          <Command.Group heading={t('cmd_sounds')}>
            {(s.sfx || []).map((name) => (
              <Command.Item key={name} value={`sound ${name} ${t(`sfx_${name}`)}`} onSelect={() => act('sfx', { name, action_id: newId() })}>
                {icons[name]} {t(`sfx_${name}`)}
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </Sheet>
  )
}

export function RiffFuel({ s, q }) {
  const { t, lang } = useLang()
  const teams = useMemo(() => Object.fromEntries(s.teams.map((x) => [x.id, x])), [s.teams])
  const chips = s.riff_fuel || []
  if (!chips.length) return null
  const opt = (i) => `${OPTION_STYLES[i].shape} ${pick(q.options[i], lang)}`
  const label = (c) => {
    switch (c.kind) {
      case 'popular': return t('fuel_popular', { opt: opt(c.option), n: c.count })
      case 'lone_wolf': return t('fuel_lone_wolf', { opt: opt(c.option) })
      case 'split': return t('fuel_split', { a: opt(c.options[0]), b: opt(c.options[1]) })
      case 'confidently_wrong': return t('fuel_confidently_wrong', { opt: opt(c.option), n: c.count })
      case 'fastest_wrong': return t('fuel_fastest_wrong', { s: (c.ms / 1000).toFixed(1), opt: opt(c.option) })
      case 'rivals': return t('fuel_rivals', { gap: c.gap })
      default: return c.kind
    }
  }
  const icons = { popular: '👥', lone_wolf: '🐺', split: '⚔️', confidently_wrong: '🤡', fastest_wrong: '⚡', rivals: '🥊' }
  return (
    <div className="panel fuel">
      <h3>⛽ {t('riff_fuel')}</h3>
      {chips.map((c, k) => (
        <div className="fuel-chip" key={k}>
          <b>{icons[c.kind]} {label(c)}</b>
          {c.teams && (
            <div className="fuel-names">
              {c.teams.slice(0, 6).map((id) => teams[id] && (
                <span key={id}>
                  {teams[id].emoji} {teams[id].name}
                  <span className={`roast-${teams[id].roast}`}> 🌶️{t(`roast_${teams[id].roast}`)}</span>
                  {teams[id].mic && ' 🎤'}
                </span>
              ))}
              {c.teams.length > 6 && <span className="muted">+{c.teams.length - 6}</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export function WriteInPanel({ s, act }) {
  const { t } = useLang()
  const teams = useMemo(() => Object.fromEntries(s.teams.map((x) => [x.id, x])), [s.teams])
  const groups = s.writeins || []
  const approved = groups.filter((g) => g.approved && !g.hidden).length
  const canEdit = ['question_open', 'question_locked'].includes(s.phase)
  return (
    <div className="panel">
      <div className="row"><h3 className="grow" style={{ margin: 0 }}>✍️ {t('writeins_title')}</h3><b>{t('approved_x', { x: approved })}</b></div>
      {s.phase === 'vote' && <p className="muted">🗳️ {t('votes_x', { x: s.answered_count, y: s.voters_count })}</p>}
      {groups.length === 0 && <p className="muted">{t('no_writeins')}</p>}
      {groups.map((g) => (
        <div key={g.gid} className={`team-row wi-row ${g.approved ? 'approved' : ''}`} style={{ opacity: g.hidden ? 0.5 : 1 }}>
          <div className="line1">
            <b className="grow" style={{ textDecoration: g.hidden ? 'line-through' : 'none' }}>“{g.text}”</b>
            {g.teams.length > 1 && <span className="tag">×{g.teams.length}</span>}
            {g.flagged && <span className="badge-warn">⚠ {g.reason || t('status_flagged')}</span>}
            {['vote', 'reveal', 'riff', 'scoreboard'].includes(s.phase) && g.approved && <b>🗳️ {g.votes}</b>}
          </div>
          <div className="muted" style={{ fontSize: 14, margin: '4px 0' }}>
            {g.teams.map((id) => `${teams[id]?.emoji || ''} ${teams[id]?.name || ''}`).join(' · ')}
          </div>
          {canEdit && (
            <div className="row">
              {g.approved
                ? <button className="btn small" onClick={() => act('wi_mod', { gid: g.gid, op: 'unapprove' })}>↩ {t('btn_unapprove')}</button>
                : <button className="btn small lime" disabled={approved >= 6} onClick={() => act('wi_mod', { gid: g.gid, op: 'approve' })}>✓ {t('btn_approve')}</button>}
              <button className="btn small" onClick={() => act('wi_mod', { gid: g.gid, op: g.hidden ? 'show' : 'hide' })}>
                {g.hidden ? `👁 ${t('btn_show')}` : `🙈 ${t('btn_hide')}`}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export function HeckleQueue({ s, act, serverNow }) {
  const { t } = useLang()
  const teams = useMemo(() => Object.fromEntries(s.teams.map((x) => [x.id, x])), [s.teams])
  const onScreen = new Set((s.effects || []).filter((e) => e.kind === 'heckle' && e.until > serverNow()).map((e) => e.ref))
  const list = (s.heckles || []).filter((h) => h.status !== 'hidden')
  const pending = list.filter((h) => h.status === 'pending').length
  return (
    <div className="panel">
      <div className="row"><h3 className="grow" style={{ margin: 0 }}>🗯️ {t('heckle_queue')}</h3>{pending > 0 && <span className="badge-warn">{pending}</span>}</div>
      {list.length === 0 && <p className="muted" style={{ marginBottom: 0 }}>{t('no_heckles')}</p>}
      {list.slice(0, 15).map((h) => {
        const tm = teams[h.team_id]
        return (
          <div key={h.id} className="team-row">
            <div className="line1">
              <b className="grow">“{h.text}”</b>
              {h.flagged && <span className="badge-warn">⚠ {h.reason || t('status_flagged')}</span>}
              {onScreen.has(h.id) && <span className="tag" style={{ color: 'var(--lime)' }}>📺 {t('on_screen_now')}</span>}
              {h.status === 'shown' && !onScreen.has(h.id) && <span className="tag muted">{t('shown')} · {t('laughs_n', { n: h.laughs })}</span>}
            </div>
            <div className="muted" style={{ fontSize: 14, margin: '4px 0' }}>{tm?.emoji} {tm?.name}</div>
            <div className="row">
              {!onScreen.has(h.id) && <button className="btn small yellow" onClick={() => act('heckle', { heckle_id: h.id, op: 'show' })}>📺 {t('btn_show_screen')}</button>}
              <button className="btn small" onClick={() => act('heckle', { heckle_id: h.id, op: 'hide' })}>🙈 {t('btn_hide')}</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function SoundBoard({ s, act }) {
  const { t } = useLang()
  const icons = { rimshot: '🥁', trombone: '🎺', airhorn: '📯', drumroll: '🪘', ding: '🔔', buzz: '❌' }
  return (
    <div className="panel">
      <h3>🔊 {t('sound_board')}</h3>
      <div className="ctl-grid">
        {(s.sfx || []).map((name) => (
          <button key={name} className="btn small" onClick={() => act('sfx', { name, action_id: newId() })}>{icons[name]} {t(`sfx_${name}`)}</button>
        ))}
      </div>
    </div>
  )
}

export function WagerPanel({ s }) {
  const { t } = useLang()
  const w = s.wager
  if (!w) return null
  return (
    <div className="panel">
      <h3>💰 {t('wager_title')}</h3>
      <p style={{ marginTop: 0 }}>{t('wager_host', { n: Object.keys(w.bets).length, y: s.team_count })}</p>
      {s.teams.map((tm) => (
        <div key={tm.id} className="row" style={{ justifyContent: 'space-between', borderTop: '1px solid var(--line)', padding: '6px 0' }}>
          <span>{tm.emoji} {tm.name} {w.bottom.includes(tm.id) && <span className="tag" style={{ color: 'var(--pink)' }}>×2</span>}</span>
          <b>{w.bets[tm.id] ?? 0}%</b>
        </div>
      ))}
    </div>
  )
}

export function AwardsPanel({ s }) {
  const { t } = useLang()
  const teams = Object.fromEntries(s.teams.map((x) => [x.id, x]))
  if (!s.awards) return null
  const icons = { champion: '🧠', funniest: '😂', confidently_wrong: '🤡', best_heckle: '🗯️' }
  return (
    <div className="panel">
      <h3>🏅 {t('awards_title')}</h3>
      {s.awards.map((a) => (
        <div key={a.key} className="team-row">
          <b>{icons[a.key]} {t(`award_${a.key}`)}</b>
          <div>{teams[a.team_id]?.emoji} {teams[a.team_id]?.name}</div>
          {a.text && <div className="muted">“{a.text}”</div>}
        </div>
      ))}
    </div>
  )
}

export function ProfilePanel({ s, act }) {
  const { t } = useLang()
  const [form, setForm] = useState(s.profile)
  useEffect(() => { setForm(s.profile) }, [s.profile])
  const fields = [['host_name', `🎤 ${t('profile_name')}`], ['zalo', '💬 Zalo'], ['facebook', '📘 Facebook'], ['instagram', '📸 Instagram'], ['tiktok', '🎵 TikTok']]
  const save = async (e) => {
    e.preventDefault()
    if (await act('profile', form)) toast.success(t('editor_saved'))
  }
  return (
    <form className="panel" onSubmit={save}>
      <h3>👋 {t('profile_title')}</h3>
      {fields.map(([k, label]) => (
        <label key={k} className="lbl" style={{ marginTop: 10 }}>{label}
          <input className="input" maxLength={60} value={form[k] || ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
        </label>
      ))}
      <button className="btn yellow block" type="submit" style={{ marginTop: 12 }}>{t('profile_save')}</button>
    </form>
  )
}

export function StarSheet({ act, open, onOpenChange, onSaved }) {
  const { t } = useLang()
  const [note, setNote] = useState('')
  const [id, setId] = useState(newId)
  const save = async (e) => {
    e.preventDefault()
    if (await act('star', { note, action_id: id })) {
      onSaved()
      setNote('')
      setId(newId())
      onOpenChange(false)
    }
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={`⭐ ${t('star_title')}`} tone="yellow">
      <form onSubmit={save}>
        <input className="input" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('star_ph')} />
        <button type="submit" className="btn yellow block" style={{ marginTop: 10 }}>⭐ {t('star_save')}</button>
      </form>
    </Sheet>
  )
}
