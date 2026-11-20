import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, deviceId, errKey } from '../api'
import { LangToggle, Toast } from '../components'
import { EMOJIS, PUN_NAMES, useLang } from '../i18n'
import { Segmented, SwitchRow } from '../ui'

export default function Join() {
  const { code: raw } = useParams()
  const code = raw.toUpperCase()
  const { t } = useLang()
  const nav = useNavigate()
  const device = deviceId()
  const [name, setName] = useState('')
  const [emoji, setEmoji] = useState(EMOJIS[0])
  const [fact, setFact] = useState('')
  const [roast, setRoast] = useState('mild')
  const [mic, setMic] = useState(false)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(true)
  const [err, setErr] = useState('')
  const [fatal, setFatal] = useState('')

  // Already joined on this device? Go straight to the game.
  useEffect(() => {
    api(`/rooms/${code}/state?role=player&device=${encodeURIComponent(device)}`)
      .then((s) => { if (s.me) nav(`/play/${code}`, { replace: true }); else setChecking(false) })
      .catch((e) => { if (e.status === 404) setFatal(t('err_room_not_found')); setChecking(false) })
  }, [code]) // eslint-disable-line react-hooks/exhaustive-deps

  const dice = () => {
    let n = name
    while (n === name) n = PUN_NAMES[Math.floor(Math.random() * PUN_NAMES.length)]
    setName(n)
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim()) { setErr(t('err_name_required')); return }
    setBusy(true)
    try {
      await api(`/rooms/${code}/join`, { method: 'POST', body: { device_id: device, name, emoji, fact, roast, mic } })
      nav(`/play/${code}`, { replace: true })
    } catch (e2) {
      setErr(t(errKey(e2)))
      setBusy(false)
    }
  }

  if (fatal) {
    return (
      <div className="page center">
        <div className="big-emoji">🤷</div>
        <p>{fatal}</p>
        <button className="btn yellow" onClick={() => nav('/')}>{t('go_home')}</button>
      </div>
    )
  }

  return (
    <div>
      <div className="topbar">
        <span className="brand">🎤 {t('join_title')}</span>
        <span className="code-pill">{code}</span>
        <LangToggle />
      </div>
      <form className="page" onSubmit={submit} style={{ opacity: checking ? 0.5 : 1 }}>
        <label className="lbl" htmlFor="tn">{t('team_name')}</label>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <input id="tn" className="input" value={name} maxLength={30} onChange={(e) => setName(e.target.value)}
            placeholder="Phở Real" autoComplete="off" />
          <button type="button" className="btn yellow" onClick={dice} aria-label={t('roll_dice')} title={t('roll_dice')}
            style={{ fontSize: 28, minWidth: 64 }}>🎲</button>
        </div>
        <p className="hint">{t('chars_left', { n: 30 - name.length })}</p>

        <label className="lbl">{t('pick_emoji')}</label>
        <Segmented className="emoji-grid" columns={6} label={t('pick_emoji')} value={emoji} onChange={setEmoji}
          options={EMOJIS.map((e) => ({ value: e, label: e }))} />

        <label className="lbl" htmlFor="ff">{t('fun_fact')}</label>
        <input id="ff" className="input" value={fact} maxLength={80} onChange={(e) => setFact(e.target.value)}
          placeholder={t('fun_fact_ph')} autoComplete="off" />
        <p className="hint">{t('fact_note')} · {t('chars_left', { n: 80 - fact.length })}</p>

        <label className="lbl">🌶️ {t('roast_level')}</label>
        <Segmented label={t('roast_level')} value={roast} onChange={setRoast}
          options={['off', 'mild', 'spicy'].map((r) => ({ value: r, label: t(`roast_${r}`) }))} />
        <p className="hint">{t('roast_help')}</p>

        <div style={{ marginTop: 18 }}>
          <SwitchRow checked={mic} onChange={setMic} label={`🎤 ${t('mic_ready')}`} hint={t('mic_help')} />
        </div>

        <div className="sticky-cta"><div className="inner">
          <button className="btn pink block" type="submit" disabled={busy || checking} style={{ fontSize: 22, minHeight: 64 }}>
            {busy ? t('joining') : `${emoji} ${t('join_button')}`}
          </button>
        </div></div>
      </form>
      <Toast msg={err} onDone={() => setErr('')} />
    </div>
  )
}
