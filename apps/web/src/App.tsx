import { useEffect, useState } from 'react'

const API_URL =
  import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

const opportunities = [
  {
    type: "Master's",
    title: 'Data Science & AI',
    school: 'Example University',
    status: 'Ready to analyse',
  },
  {
    type: 'PhD',
    title: 'Computer Science',
    school: 'Sample Institute',
    status: 'Profile needed',
  },
]

export default function App() {
  const [apiStatus, setApiStatus] = useState('CONNECTING TO API...')

  useEffect(() => {
    const controller = new AbortController()

    async function checkApi() {
      try {
        const response = await fetch(`${API_URL}/health`, {
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`API returned ${response.status}`)
        }

        setApiStatus('API CONNECTED')
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          setApiStatus('API OFFLINE')
        }
      }
    }

    void checkApi()

    return () => controller.abort()
  }, [])

  return (
    <main>
      <nav>
        <strong>
          ApplyLens <span>AI</span>
        </strong>
        <button className="ghost">View roadmap</button>
      </nav>

      <section className="hero">
        <div>
          <p className="eyebrow">
            APPLICATION INTELLIGENCE • {apiStatus}
          </p>
          <h1>
            Know where you qualify.
            <br />
            See the evidence.
          </h1>
          <p className="lead">
            Upload your profile and a Master's or PhD call. ApplyLens turns
            long documents into clear eligibility decisions, citations, and
            an application checklist.
          </p>
          <div className="actions">
            <button>Analyse an opportunity</button>
            <button className="ghost">Build my profile</button>
          </div>
        </div>

        <div className="decision-card">
          <p className="muted">ELIGIBILITY PREVIEW</p>
          <h2>Evidence, not guesses</h2>

          {[
            'Degree requirement',
            'English evidence',
            'Application fee',
            'Deadline',
          ].map((item, index) => (
            <div className="decision" key={item}>
              <span className={`dot d${index}`}></span>
              <div>
                <strong>{item}</strong>
                <small>
                  {
                    [
                      'Eligible — evidence found',
                      'Unclear — certificate needed',
                      'Action required — €20',
                      'Confirmed — 24 July',
                    ][index]
                  }
                </small>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="workspace">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h2>Applications at a glance</h2>
        </div>

        <div className="stats">
          <article>
            <strong>2</strong>
            <span>Opportunities</span>
          </article>
          <article>
            <strong>1</strong>
            <span>Deadline tracked</span>
          </article>
          <article>
            <strong>0</strong>
            <span>Calls analysed</span>
          </article>
        </div>

        <div className="grid">
          {opportunities.map((opportunity) => (
            <article className="opportunity" key={opportunity.title}>
              <span className="tag">{opportunity.type}</span>
              <h3>{opportunity.title}</h3>
              <p>{opportunity.school}</p>
              <footer>
                <span>{opportunity.status}</span>
                <button aria-label={`Open ${opportunity.title}`}>→</button>
              </footer>
            </article>
          ))}
        </div>
      </section>

      <footer className="page-footer">
        Built by Oumaima Ouayres • Sprint 0 • Master's and PhD MVP
      </footer>
    </main>
  )
}