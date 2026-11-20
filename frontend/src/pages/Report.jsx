import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errKey, hostKey } from '../api'
import { LangToggle, OPTION_STYLES } from '../components'
import { pick, useLang } from '../i18n'

function bitTitle(b, t, lang) {
  const kind = t(`bit_${b.kind}`)
  const label = typeof b.label === 'object' ? pick(b.label, lang) : (b.label || '')
  return `${kind}: ${label}`
}

function toMarkdown(data, t, lang) {
  const date = new Date(data.created_at).toLocaleDateString(lang === 'vi' ? 'vi-VN' : 'en-GB')
  const line = (b) => `- **${bitTitle(b, t, lang)}** · ${b.score} ${t('laughs_per_team')} · ${t('laughs_n', { n: b.laughs })} · ${t('groans_n', { n: b.groans })} · ${b.duration_s}s${b.rating != null ? ` · ⭐ ${b.rating}/5 (${b.ratings})` : ''}`
  const out = [`# Heckle & Hint · ${t('report_title')} · ${data.code} · ${date}`, '']
  out.push(`## ✅ ${t('report_keep')}`, ...(data.keep.length ? data.keep.map(line) : [`- ${t('report_none')}`]), '')
  out.push(`## 🔧 ${t('report_rework')}`, ...(data.rework.length ? data.rework.map(line) : ['-']), '')
  out.push(`## ⭐ ${t('report_stars')}`)
  out.push(...(data.stars.length ? data.stars.map((s) => {
    const time = new Date(s.at).toLocaleTimeString(lang === 'vi' ? 'vi-VN' : 'en-GB', { hour: '2-digit', minute: '2-digit' })
    const label = s.label ? (typeof s.label === 'object' ? pick(s.label, lang) : s.label) : ''
    return `- ${time}${label ? ` · ${label}` : ''}${s.note ? ` — ${s.note}` : ''}`
  }) : ['-']), '')
  out.push(`## 😂 ${t('report_bits')}`, ...(data.bits.length ? data.bits.map(line) : ['-']), '')
  out.push(`## ❓ ${t('report_questions')}`)
  for (const q of data.questions) {
    if (!q.played) continue
    const pct = q.type === 'quiz' ? ` · ${Math.round((q.correct_count / Math.max(1, q.answers)) * 100)}% ${t('report_correct')}` : ''
    out.push(`- ${pick(q.text, lang)} · ${q.answers} ${t('report_answers')}${pct}`)
  }
  return out.join('\n')
}

export default function Report() {
  const { code: raw } = useParams()
  const code = raw.toUpperCase()
  const { t, lang } = useLang()
  const key = hostKey.get(code)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!key) { setErr('err_not_host'); return }
    api(`/rooms/${code}/report`, { key }).then(setData).catch((e) => setErr(errKey(e)))
  }, [code, key])

  const md = data ? toMarkdown(data, t, lang) : ''
  const copy = async () => {
    try { await navigator.clipboard.writeText(md); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* no clipboard */ }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([md], { type: 'text/markdown;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `heckle-hint-${code}-set-report.md`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const BitRow = ({ b, i }) => (
    <div className="team-row">
      <div className="line1">
        {i != null && <b style={{ color: 'var(--yellow)' }}>#{i + 1}</b>}
        <span className="grow"><b>{bitTitle(b, t, lang)}</b></span>
        <b>{b.score}</b><span className="muted" style={{ fontSize: 13 }}>{t('laughs_per_team')}</span>
      </div>
      <div className="muted" style={{ fontSize: 14 }}>😂 {t('laughs_n', { n: b.laughs })} · 😩 {t('groans_n', { n: b.groans })} · ⏱ {b.duration_s}s
        {b.rating != null && <> · ⭐ {t('rating_label')} {b.rating}/5 ({b.ratings})</>}</div>
    </div>
  )

  return (
    <div>
      <div className="topbar"><span className="brand">📋 {t('report_title')}</span><span className="code-pill">{code}</span><LangToggle /></div>
      <div className="page">
        <p className="muted">{t('report_tier1')}</p>
        {err && <p>{t(err)}</p>}
        {!data && !err && <p className="muted">{t('loading')}</p>}
        {data && (
          <>
            <div className="row">
              <button className="btn yellow grow" onClick={copy}>📋 {copied ? t('copied') : t('copy_md')}</button>
              <button className="btn grow" onClick={download}>⬇️ {t('download_md')}</button>
            </div>
            <div className="panel">
              <h3>✅ {t('report_keep')}</h3>
              {data.keep.length ? data.keep.map((b, i) => <BitRow key={b.id} b={b} i={i} />) : <p className="muted">{t('report_none')}</p>}
            </div>
            {data.rework.length > 0 && (
              <div className="panel">
                <h3>🔧 {t('report_rework')}</h3>
                {data.rework.map((b) => <BitRow key={b.id} b={b} />)}
              </div>
            )}
            <div className="panel">
              <h3>⭐ {t('report_stars')}</h3>
              {data.stars.length === 0 && <p className="muted">-</p>}
              {data.stars.map((s) => (
                <div className="team-row" key={s.id}>
                  <b>{new Date(s.at).toLocaleTimeString(lang === 'vi' ? 'vi-VN' : 'en-GB', { hour: '2-digit', minute: '2-digit' })}</b>
                  {s.label && <span className="muted"> · {typeof s.label === 'object' ? pick(s.label, lang) : s.label}</span>}
                  {s.note && <div>“{s.note}”</div>}
                </div>
              ))}
            </div>
            <div className="panel">
              <h3>😂 {t('report_bits')}</h3>
              {data.bits.length ? data.bits.map((b, i) => <BitRow key={b.id} b={b} i={i} />) : <p className="muted">{t('report_none')}</p>}
            </div>
            <div className="panel">
              <h3>❓ {t('report_questions')}</h3>
              <table className="report">
                <tbody>
                  {data.questions.map((q) => {
                    const top = q.answers && q.type !== 'writein' ? q.counts.indexOf(Math.max(...q.counts)) : -1
                    return (
                      <tr key={q.i}>
                        <td><b>{q.type === 'poll' ? t('poll_tag') : q.type === 'writein' ? t('writein_tag') : `Q${q.i + 1}`}</b></td>
                        <td>
                          {pick(q.text, lang)}
                          <div className="muted" style={{ fontSize: 14 }}>
                            {!q.played ? t('report_not_played') : (
                              <>
                                {q.answers} {t('report_answers')}
                                {q.type === 'quiz' && <> · {Math.round((q.correct_count / Math.max(1, q.answers)) * 100)}% {t('report_correct')}</>}
                                {top >= 0 && <> · {t('report_popular')}: {OPTION_STYLES[top].shape} {pick(q.options[top], lang)}</>}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
        <Link className="btn ghost" to={`/host/${code}`}>← {t('back_to_console')}</Link>
      </div>
    </div>
  )
}
