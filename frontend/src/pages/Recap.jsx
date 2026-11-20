import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errKey } from '../api'
import { Follow, LangToggle, teamLabel } from '../components'
import { useLang } from '../i18n'

export default function Recap() {
  const { code: raw } = useParams()
  const code = raw.toUpperCase()
  const { t } = useLang()
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    const load = () => api(`/rooms/${code}/recap`).then((d) => alive && setData(d)).catch((e) => alive && setErr(errKey(e)))
    load()
    const id = setInterval(load, 10000) // the recap fills in as the night goes on
    return () => { alive = false; clearInterval(id) }
  }, [code])

  const medals = ['🥇', '🥈', '🥉']
  const icons = { champion: '🧠', funniest: '😂', confidently_wrong: '🤡', best_heckle: '🗯️' }
  return (
    <div>
      <div className="topbar"><span className="brand">🎤 {t('app_name')}</span><span className="code-pill">{code}</span><LangToggle /></div>
      <div className="page">
        <h1 style={{ color: 'var(--pink)', fontSize: 34 }}>{t('recap_title')}</h1>
        {err && <p>{t(err)}</p>}
        {!data && !err && <p className="muted">{t('loading')}</p>}
        {data && (
          <>
            <div className="panel">
              <h3>🏆 {t('recap_top3')}</h3>
              {data.top.length === 0 ? <p className="muted">{t('recap_empty')}</p> : (
                <div className="podium">
                  {data.top.map((tm, i) => (
                    <div className="p" key={tm.id}>
                      <span style={{ fontSize: 34 }}>{medals[i]}</span>
                      <span className="grow">{tm.emoji} {teamLabel(tm, t)}</span>
                      <span>{tm.total}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {data.best_heckle && (
              <div className="panel">
                <h3>🗯️ {t('recap_best_heckle')}</h3>
                <p style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>“{data.best_heckle.text}”</p>
                <p className="muted">— {data.best_heckle.team?.emoji} {teamLabel(data.best_heckle.team, t)}</p>
              </div>
            )}
            {data.funniest_answer && (
              <div className="panel">
                <h3>😂 {t('recap_funniest')}</h3>
                <p style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>“{data.funniest_answer.text}”</p>
                <p className="muted">— {data.funniest_answer.teams.map((x) => `${x.emoji} ${teamLabel(x, t)}`).join(', ')} · {data.funniest_answer.votes} {t('votes')}</p>
              </div>
            )}
            {data.awards.length > 0 && (
              <div className="panel">
                <h3>🏅 {t('awards_title')}</h3>
                {data.awards.map((a) => (
                  <div className="team-row" key={a.key}>
                    <b>{icons[a.key]} {t(`award_${a.key}`)}</b>
                    <div>{a.team?.emoji} {teamLabel(a.team, t)}</div>
                  </div>
                ))}
              </div>
            )}
            {Object.keys(data.profile || {}).length > 0 && <Follow profile={data.profile} code={code} />}
          </>
        )}
        <Link className="btn ghost" to="/">← {t('go_home')}</Link>
      </div>
    </div>
  )
}
