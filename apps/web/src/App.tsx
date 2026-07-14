const opportunities = [
  { type: "Master's", title: 'Data Science & AI', school: 'Example University', status: 'Ready to analyse' },
  { type: 'PhD', title: 'Computer Science', school: 'Sample Institute', status: 'Profile needed' },
]

export default function App() {
  return (
    <main>
      <nav><strong>ApplyLens <span>AI</span></strong><button className="ghost">View roadmap</button></nav>
      <section className="hero">
        <div><p className="eyebrow">APPLICATION INTELLIGENCE</p><h1>Know where you qualify.<br/>See the evidence.</h1><p className="lead">Upload your profile and a Master's or PhD call. ApplyLens turns long documents into clear eligibility decisions, citations, and an application checklist.</p><div className="actions"><button>Analyse an opportunity</button><button className="ghost">Build my profile</button></div></div>
        <div className="decision-card"><p className="muted">ELIGIBILITY PREVIEW</p><h2>Evidence, not guesses</h2>{['Degree requirement','English evidence','Application fee','Deadline'].map((item, i)=><div className="decision" key={item}><span className={`dot d${i}`}></span><div><strong>{item}</strong><small>{['Eligible — evidence found','Unclear — certificate needed','Action required — €20','Confirmed — 24 July'][i]}</small></div></div>)}</div>
      </section>
      <section className="workspace"><div><p className="eyebrow">YOUR WORKSPACE</p><h2>Applications at a glance</h2></div><div className="stats"><article><strong>2</strong><span>Opportunities</span></article><article><strong>1</strong><span>Deadline tracked</span></article><article><strong>0</strong><span>Calls analysed</span></article></div><div className="grid">{opportunities.map(x=><article className="opportunity" key={x.title}><span className="tag">{x.type}</span><h3>{x.title}</h3><p>{x.school}</p><footer><span>{x.status}</span><button aria-label={`Open ${x.title}`}>→</button></footer></article>)}</div></section>
      <footer className="page-footer">Sprint 0 prototype • Master's and PhD MVP</footer>
    </main>
  )
}

