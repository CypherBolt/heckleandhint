import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errKey, hostKey } from '../api'
import { LangToggle, Toast } from '../components'
import { useLang } from '../i18n'

const CODE_RE = /^[A-HJ-NP-Z]{4}$/

export default function Landing() {
  const { t } = useLang()
  const nav = useNavigate()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const host = async () => {
    setBusy(true)
    try {
      const r = await api('/rooms', { method: 'POST', retries: 2 })
      hostKey.set(r.code, r.host_key)
      nav(`/host/${r.code}?key=${encodeURIComponent(r.host_key)}`)
    } catch (e) {
      setErr(t(errKey(e)))
      setBusy(false)
    }
  }

  const clean = code.toUpperCase().replace(/[^A-Z]/g, '').replace(/[IO]/g, '').slice(0, 4)
  const join = (e) => {
    e.preventDefault()
    if (CODE_RE.test(clean)) nav(`/join/${clean}`)
  }

  return (
    <div className="landing">
      <div className="topbar"><span className="brand">🎤 {t('app_name')}</span><LangToggle /></div>
      <div className="hero">
        <h1>Heckle <span>&</span> Hint</h1>
        <p>{t('tagline')}</p>
        <button className="btn pink block" onClick={host} disabled={busy} style={{ marginTop: 24, fontSize: 22 }}>
          🎤 {busy ? t('creating') : t('host_a_night')}
        </button>
        <form onSubmit={join} className="panel" style={{ marginTop: 28 }}>
          <h3>{t('join_with_code')}</h3>
          <input className="input code-input" value={clean} onChange={(e) => setCode(e.target.value)}
            placeholder="ABCD" aria-label={t('room_code')} autoCapitalize="characters" autoComplete="off" />
          <p className="hint">{t('code_hint')}</p>
          <button className="btn yellow block" type="submit" disabled={!CODE_RE.test(clean)} style={{ marginTop: 12 }}>
            {t('join_go')} →
          </button>
        </form>
        <p className="hint center">{t('no_personal')}</p>
      </div>
      <Toast msg={err} onDone={() => setErr('')} />
    </div>
  )
}
