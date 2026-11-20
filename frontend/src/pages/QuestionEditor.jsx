// Host question editor. Questions already played are locked; the finale is always last.
import { useEffect, useState } from 'react'
import { api, errKey } from '../api'
import { OPTION_STYLES } from '../components'
import { pick, useLang } from '../i18n'
import { Segmented, toast } from '../ui'

const blankOpt = () => ({ en: '', vi: '' })
const blank = () => ({
  type: 'quiz', text: { en: '', vi: '' }, options: [blankOpt(), blankOpt(), blankOpt(), blankOpt()], correct: 0,
  time_limit: 20, setup: { en: '', vi: '' }, punchline: { en: '', vi: '' }, notes: '',
})

export default function QuestionEditor({ code, hostKey, onToast, version }) {
  const { t, lang } = useLang()
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [editing, setEditing] = useState(null) // index in `upcoming`, 'final', or 'new'
  const [draft, setDraft] = useState(null)

  const load = async () => {
    try { setData(await api(`/rooms/${code}/questions`, { key: hostKey })) } catch (e) { onToast(t(errKey(e))) }
  }
  useEffect(() => { if (open && editing == null) load() }, [open, version]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) {
    return <button className="btn block" style={{ marginTop: 14 }} onClick={() => setOpen(true)}>📝 {t('editor_open')}</button>
  }
  if (!data) return <div className="panel muted">{t('loading')}</div>

  const all = data.questions
  const played = all.filter((q) => q.locked && !q.final)
  const upcoming = all.filter((q) => !q.locked && !q.final)
  const final = all.find((q) => q.final)

  const save = async (list, fin) => {
    try {
      await api(`/rooms/${code}/host/questions`, { method: 'POST', key: hostKey, body: { questions: list, final: fin } })
      await load()
      toast.success(t('editor_saved'))
      return true
    } catch (e) {
      onToast(t(errKey(e)))
      return false
    }
  }
  const move = (i, d) => {
    const list = [...upcoming]
    const j = i + d
    if (j < 0 || j >= list.length) return
    ;[list[i], list[j]] = [list[j], list[i]]
    save(list, final)
  }
  const del = (i) => save(upcoming.filter((_, k) => k !== i), final)
  const startEdit = (which) => {
    setEditing(which)
    const src = which === 'new' ? blank() : which === 'final' ? final : upcoming[which]
    const d = JSON.parse(JSON.stringify(src))
    if (!d.options || d.options.length !== 4) d.options = [blankOpt(), blankOpt(), blankOpt(), blankOpt()]
    if (d.correct == null) d.correct = 0
    setDraft(d)
  }
  const commit = async () => {
    const list = [...upcoming]
    let fin = final
    if (editing === 'new') list.push(draft)
    else if (editing === 'final') fin = draft
    else list[editing] = draft
    if (await save(list, fin)) { setEditing(null); setDraft(null) }
  }

  if (editing != null && draft) {
    return <Form draft={draft} setDraft={setDraft} isFinal={editing === 'final'} onSave={commit}
      onCancel={() => { setEditing(null); setDraft(null) }} />
  }

  const row = (q, label, actions) => (
    <div className="team-row" key={label + q.i}>
      <div className="line1">
        <span className="tag">{label}</span>
        <span className="tag muted">{t(`type_${q.type}`)}</span>
        <span className="grow" style={{ minWidth: 0 }}>{pick(q.text, lang)}</span>
      </div>
      {actions && <div className="row" style={{ marginTop: 6 }}>{actions}</div>}
    </div>
  )

  return (
    <div className="panel">
      <div className="row"><h3 className="grow" style={{ margin: 0 }}>📝 {t('editor_title')}</h3>
        <button className="btn small ghost" onClick={() => setOpen(false)}>✕ {t('editor_close')}</button></div>
      {!data.editable && <p className="badge-warn" style={{ padding: 8 }}>{t('editor_locked')}</p>}
      {played.map((q) => row(q, `Q${q.i + 1} · ${t('editor_played')}`, null))}
      {upcoming.map((q, i) => row(q, `Q${q.i + 1}`, data.editable && (
        <>
          <button className="btn small" onClick={() => startEdit(i)}>✏️ {t('editor_edit')}</button>
          <button className="btn small" onClick={() => move(i, -1)} disabled={i === 0} aria-label={t('editor_up')}>↑</button>
          <button className="btn small" onClick={() => move(i, 1)} disabled={i === upcoming.length - 1} aria-label={t('editor_down')}>↓</button>
          <button className="btn small red" onClick={() => del(i)}>🗑 {t('editor_delete')}</button>
        </>
      )))}
      {final && row(final, `🏆 ${t('editor_finale')}`, data.editable && !final.locked && (
        <button className="btn small" onClick={() => startEdit('final')}>✏️ {t('editor_edit')}</button>
      ))}
      {data.editable && <button className="btn yellow block" style={{ marginTop: 12 }} onClick={() => startEdit('new')}>{t('editor_add')}</button>}
    </div>
  )
}

function Bil({ label, value, onChange, max, area }) {
  const Tag = area ? 'textarea' : 'input'
  return (
    <div style={{ marginTop: 10 }}>
      <label className="lbl" style={{ margin: '0 0 4px' }}>{label}</label>
      <Tag className="input" rows={area ? 2 : undefined} maxLength={max} placeholder="EN" value={value?.en || ''}
        onChange={(e) => onChange({ ...value, en: e.target.value })} />
      <Tag className="input" rows={area ? 2 : undefined} maxLength={max} placeholder="VI" value={value?.vi || ''}
        style={{ marginTop: 4 }} onChange={(e) => onChange({ ...value, vi: e.target.value })} />
    </div>
  )
}

function Form({ draft, setDraft, isFinal, onSave, onCancel }) {
  const { t } = useLang()
  const set = (k, v) => setDraft({ ...draft, [k]: v })
  return (
    <div className="panel">
      <h3>📝 {isFinal ? t('editor_finale') : t('editor_question')}</h3>
      {!isFinal && (
        <Segmented label={t('editor_type')} value={draft.type} onChange={(v) => set('type', v)}
          options={['quiz', 'poll', 'writein'].map((k) => ({ value: k, label: t(`type_${k}`) }))} />
      )}
      <Bil label={t('editor_question')} value={draft.text} onChange={(v) => set('text', v)} max={200} area />
      {draft.type !== 'writein' && draft.options.map((o, i) => (
        <div key={i} style={{ borderLeft: `6px solid ${OPTION_STYLES[i].color}`, paddingLeft: 8 }}>
          <Bil label={`${OPTION_STYLES[i].shape} ${t('editor_option', { n: i + 1 })}`} value={o} max={80}
            onChange={(v) => set('options', draft.options.map((x, k) => (k === i ? v : x)))} />
          {draft.type === 'quiz' && (
            <button type="button" className={`btn small ${draft.correct === i ? 'lime' : 'ghost'}`} style={{ marginTop: 4 }}
              onClick={() => set('correct', i)} aria-pressed={draft.correct === i}>
              {draft.correct === i ? '✅' : '○'} {t('editor_correct')}
            </button>
          )}
        </div>
      ))}
      <label className="lbl">{t('editor_seconds')}
        <input className="input" type="number" min={10} max={120} value={draft.time_limit}
          onChange={(e) => set('time_limit', Number(e.target.value) || 20)} />
      </label>
      <Bil label={t('setup_label')} value={draft.setup} onChange={(v) => set('setup', v)} max={300} area />
      <Bil label={t('punchline_label')} value={draft.punchline} onChange={(v) => set('punchline', v)} max={300} area />
      <label className="lbl">{t('notes_label')}
        <textarea className="input" rows={2} maxLength={500} value={draft.notes || ''} onChange={(e) => set('notes', e.target.value)} />
      </label>
      <div className="row" style={{ marginTop: 12, flexWrap: 'nowrap' }}>
        <button className="btn ghost" onClick={onCancel}>{t('cancel')}</button>
        <button className="btn pink grow" onClick={onSave}>💾 {t('editor_save')}</button>
      </div>
    </div>
  )
}
