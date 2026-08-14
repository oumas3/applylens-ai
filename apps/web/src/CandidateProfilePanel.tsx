import { useEffect, useState, type FormEvent } from 'react'

type DocumentOption = {
  id: string
  original_filename: string
}

type EvidenceLinked = {
  id: string
  document_ids: string[]
}

type YearRange = EvidenceLinked & {
  start_year?: number | null
  end_year?: number | null
}

type EducationItem = YearRange & {
  institution: string
  degree: string
  field_of_study?: string | null
  grade?: string | null
}

type WorkExperienceItem = YearRange & {
  organization: string
  role: string
  description?: string | null
}

type ResearchExperienceItem = YearRange & {
  title: string
  organization?: string | null
  description?: string | null
}

type LanguageItem = EvidenceLinked & {
  name: string
  proficiency: 'basic' | 'intermediate' | 'professional' | 'fluent' | 'native'
}

type SkillItem = EvidenceLinked & {
  name: string
}

type PublicationItem = EvidenceLinked & {
  title: string
  venue?: string | null
  year?: number | null
  url?: string | null
}

type CandidateProfileDraft = {
  full_name: string
  headline: string
  location: string
  summary: string
  education: EducationItem[]
  work_experience: WorkExperienceItem[]
  research_experience: ResearchExperienceItem[]
  languages: LanguageItem[]
  skills: SkillItem[]
  publications: PublicationItem[]
}

type ProfileCollectionKey =
  | 'education'
  | 'work_experience'
  | 'research_experience'
  | 'languages'
  | 'skills'
  | 'publications'

const EMPTY_PROFILE: CandidateProfileDraft = {
  full_name: '',
  headline: '',
  location: '',
  summary: '',
  education: [],
  work_experience: [],
  research_experience: [],
  languages: [],
  skills: [],
  publications: [],
}

function itemId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`
}

function normalizedProfile(payload: Partial<CandidateProfileDraft>): CandidateProfileDraft {
  return {
    full_name: payload.full_name ?? '',
    headline: payload.headline ?? '',
    location: payload.location ?? '',
    summary: payload.summary ?? '',
    education: payload.education ?? [],
    work_experience: payload.work_experience ?? [],
    research_experience: payload.research_experience ?? [],
    languages: payload.languages ?? [],
    skills: payload.skills ?? [],
    publications: payload.publications ?? [],
  }
}

function optionalYear(value: string): number | null {
  return value ? Number(value) : null
}

function EvidenceDocuments({
  documents,
  value,
  onChange,
}: {
  documents: DocumentOption[]
  value: string[]
  onChange: (documentIds: string[]) => void
}) {
  return (
    <label className="profile-field evidence-documents">
      <span>Evidence documents</span>
      <select
        multiple
        value={value}
        onChange={(event) =>
          onChange(Array.from(event.currentTarget.selectedOptions, (option) => option.value))
        }
      >
        {documents.map((document) => (
          <option value={document.id} key={document.id}>
            {document.original_filename}
          </option>
        ))}
      </select>
      <small>Only claims linked to an uploaded document support eligibility decisions.</small>
    </label>
  )
}

export default function CandidateProfilePanel({
  apiUrl,
  documents,
  documentsReady,
}: {
  apiUrl: string
  documents: DocumentOption[]
  documentsReady: boolean
}) {
  const [profile, setProfile] = useState<CandidateProfileDraft>(EMPTY_PROFILE)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('Loading your candidate profile...')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${apiUrl}/api/v1/profile`, {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => null)
        if (!response.ok) throw new Error(payload?.detail ?? 'Unable to load your profile.')
        setProfile(normalizedProfile(payload))
        setStatus('Profile ready. Link claims to documents before using them as evidence.')
      })
      .catch((error) => {
        if ((error as Error).name !== 'AbortError') {
          setStatus(error instanceof Error ? error.message : 'Unable to load your profile.')
        }
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [apiUrl])

  useEffect(() => {
    if (loading || !documentsReady) return
    const validDocumentIds = new Set(documents.map((document) => document.id))
    setProfile((current) => {
      const cleanItems = <T extends EvidenceLinked>(items: T[]) =>
        items.map((item) => ({
          ...item,
          document_ids: item.document_ids.filter((id) => validDocumentIds.has(id)),
        }))
      return {
        ...current,
        education: cleanItems(current.education),
        work_experience: cleanItems(current.work_experience),
        research_experience: cleanItems(current.research_experience),
        languages: cleanItems(current.languages),
        skills: cleanItems(current.skills),
        publications: cleanItems(current.publications),
      }
    })
  }, [documents, documentsReady, loading])

  function updateItem<K extends ProfileCollectionKey>(
    key: K,
    index: number,
    changes: Partial<CandidateProfileDraft[K][number]>
  ) {
    setProfile((current) => ({
      ...current,
      [key]: current[key].map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...changes } : item
      ),
    }))
  }

  function addItem<K extends ProfileCollectionKey>(
    key: K,
    item: CandidateProfileDraft[K][number]
  ) {
    setProfile((current) => ({ ...current, [key]: [...current[key], item] }))
  }

  function removeItem(key: ProfileCollectionKey, index: number) {
    setProfile((current) => ({
      ...current,
      [key]: current[key].filter((_, itemIndex) => itemIndex !== index),
    }))
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setStatus('Saving your profile...')
    try {
      const response = await fetch(`${apiUrl}/api/v1/profile`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = payload?.detail
        throw new Error(
          typeof detail === 'string'
            ? detail
            : detail?.message ?? 'Unable to save your profile.'
        )
      }
      setProfile(normalizedProfile(payload))
      setStatus('Profile saved. Evidence-linked claims are ready for analysis.')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to save your profile.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="profile-section" id="candidate-profile" aria-labelledby="profile-heading">
      <div className="profile-heading">
        <div>
          <p className="eyebrow">CANDIDATE PROFILE</p>
          <h2 id="profile-heading">Build reusable, evidence-linked credentials</h2>
          <p className="analysis-status">
            Enter structured facts once. ApplyLens automatically includes supported profile
            claims when it checks a Master's or PhD opportunity.
          </p>
        </div>
        <span className="task-count">
          {profile.education.length + profile.work_experience.length +
            profile.research_experience.length + profile.languages.length +
            profile.skills.length + profile.publications.length}{' '}
          profile items
        </span>
      </div>

      <form className="profile-form" onSubmit={saveProfile}>
        <div className="profile-basics">
          <label className="profile-field">
            <span>Full name</span>
            <input value={profile.full_name} onChange={(event) => setProfile({ ...profile, full_name: event.target.value })} />
          </label>
          <label className="profile-field">
            <span>Professional headline</span>
            <input value={profile.headline} onChange={(event) => setProfile({ ...profile, headline: event.target.value })} placeholder="AI research candidate" />
          </label>
          <label className="profile-field">
            <span>Location</span>
            <input value={profile.location} onChange={(event) => setProfile({ ...profile, location: event.target.value })} />
          </label>
          <label className="profile-field profile-wide">
            <span>Profile summary</span>
            <textarea value={profile.summary} onChange={(event) => setProfile({ ...profile, summary: event.target.value })} rows={3} />
          </label>
        </div>

        <details className="profile-group" open>
          <summary>Education ({profile.education.length})</summary>
          {profile.education.map((item, index) => (
            <div className="profile-item" key={item.id}>
              <label className="profile-field"><span>Degree</span><input value={item.degree} onChange={(event) => updateItem('education', index, { degree: event.target.value })} required /></label>
              <label className="profile-field"><span>Field of study</span><input value={item.field_of_study ?? ''} onChange={(event) => updateItem('education', index, { field_of_study: event.target.value })} /></label>
              <label className="profile-field"><span>Institution</span><input value={item.institution} onChange={(event) => updateItem('education', index, { institution: event.target.value })} required /></label>
              <label className="profile-field"><span>Grade</span><input value={item.grade ?? ''} onChange={(event) => updateItem('education', index, { grade: event.target.value })} /></label>
              <label className="profile-field"><span>Start year</span><input type="number" min="1900" max="2100" value={item.start_year ?? ''} onChange={(event) => updateItem('education', index, { start_year: optionalYear(event.target.value) })} /></label>
              <label className="profile-field"><span>End year</span><input type="number" min="1900" max="2100" value={item.end_year ?? ''} onChange={(event) => updateItem('education', index, { end_year: optionalYear(event.target.value) })} /></label>
              <EvidenceDocuments documents={documents} value={item.document_ids} onChange={(document_ids) => updateItem('education', index, { document_ids })} />
              <button className="ghost remove-item" type="button" onClick={() => removeItem('education', index)}>Remove education</button>
            </div>
          ))}
          <button className="ghost" type="button" onClick={() => addItem('education', { id: itemId('education'), institution: '', degree: '', document_ids: [] })}>Add education</button>
        </details>

        <details className="profile-group">
          <summary>Work experience ({profile.work_experience.length})</summary>
          {profile.work_experience.map((item, index) => (
            <div className="profile-item" key={item.id}>
              <label className="profile-field"><span>Role</span><input value={item.role} onChange={(event) => updateItem('work_experience', index, { role: event.target.value })} required /></label>
              <label className="profile-field"><span>Organization</span><input value={item.organization} onChange={(event) => updateItem('work_experience', index, { organization: event.target.value })} required /></label>
              <label className="profile-field profile-wide"><span>Description</span><textarea value={item.description ?? ''} onChange={(event) => updateItem('work_experience', index, { description: event.target.value })} rows={2} /></label>
              <label className="profile-field"><span>Start year</span><input type="number" min="1900" max="2100" value={item.start_year ?? ''} onChange={(event) => updateItem('work_experience', index, { start_year: optionalYear(event.target.value) })} /></label>
              <label className="profile-field"><span>End year</span><input type="number" min="1900" max="2100" value={item.end_year ?? ''} onChange={(event) => updateItem('work_experience', index, { end_year: optionalYear(event.target.value) })} /></label>
              <EvidenceDocuments documents={documents} value={item.document_ids} onChange={(document_ids) => updateItem('work_experience', index, { document_ids })} />
              <button className="ghost remove-item" type="button" onClick={() => removeItem('work_experience', index)}>Remove work experience</button>
            </div>
          ))}
          <button className="ghost" type="button" onClick={() => addItem('work_experience', { id: itemId('work'), organization: '', role: '', document_ids: [] })}>Add work experience</button>
        </details>

        <details className="profile-group">
          <summary>Research experience ({profile.research_experience.length})</summary>
          {profile.research_experience.map((item, index) => (
            <div className="profile-item" key={item.id}>
              <label className="profile-field"><span>Research title</span><input value={item.title} onChange={(event) => updateItem('research_experience', index, { title: event.target.value })} required /></label>
              <label className="profile-field"><span>Organization</span><input value={item.organization ?? ''} onChange={(event) => updateItem('research_experience', index, { organization: event.target.value })} /></label>
              <label className="profile-field profile-wide"><span>Description</span><textarea value={item.description ?? ''} onChange={(event) => updateItem('research_experience', index, { description: event.target.value })} rows={2} /></label>
              <label className="profile-field"><span>Start year</span><input type="number" min="1900" max="2100" value={item.start_year ?? ''} onChange={(event) => updateItem('research_experience', index, { start_year: optionalYear(event.target.value) })} /></label>
              <label className="profile-field"><span>End year</span><input type="number" min="1900" max="2100" value={item.end_year ?? ''} onChange={(event) => updateItem('research_experience', index, { end_year: optionalYear(event.target.value) })} /></label>
              <EvidenceDocuments documents={documents} value={item.document_ids} onChange={(document_ids) => updateItem('research_experience', index, { document_ids })} />
              <button className="ghost remove-item" type="button" onClick={() => removeItem('research_experience', index)}>Remove research experience</button>
            </div>
          ))}
          <button className="ghost" type="button" onClick={() => addItem('research_experience', { id: itemId('research'), title: '', document_ids: [] })}>Add research experience</button>
        </details>

        <details className="profile-group">
          <summary>Languages and skills ({profile.languages.length + profile.skills.length})</summary>
          {profile.languages.map((item, index) => (
            <div className="profile-item compact" key={item.id}>
              <label className="profile-field"><span>Language</span><input value={item.name} onChange={(event) => updateItem('languages', index, { name: event.target.value })} required /></label>
              <label className="profile-field"><span>Proficiency</span><select value={item.proficiency} onChange={(event) => updateItem('languages', index, { proficiency: event.target.value as LanguageItem['proficiency'] })}><option value="basic">Basic</option><option value="intermediate">Intermediate</option><option value="professional">Professional</option><option value="fluent">Fluent</option><option value="native">Native</option></select></label>
              <EvidenceDocuments documents={documents} value={item.document_ids} onChange={(document_ids) => updateItem('languages', index, { document_ids })} />
              <button className="ghost remove-item" type="button" onClick={() => removeItem('languages', index)}>Remove language</button>
            </div>
          ))}
          <button className="ghost" type="button" onClick={() => addItem('languages', { id: itemId('language'), name: '', proficiency: 'intermediate', document_ids: [] })}>Add language</button>
          {profile.skills.map((item, index) => (
            <div className="profile-item compact" key={item.id}>
              <label className="profile-field"><span>Skill name</span><input value={item.name} onChange={(event) => updateItem('skills', index, { name: event.target.value })} required /></label>
              <EvidenceDocuments documents={documents} value={item.document_ids} onChange={(document_ids) => updateItem('skills', index, { document_ids })} />
              <button className="ghost remove-item" type="button" onClick={() => removeItem('skills', index)}>Remove skill</button>
            </div>
          ))}
          <button className="ghost" type="button" onClick={() => addItem('skills', { id: itemId('skill'), name: '', document_ids: [] })}>Add skill</button>
        </details>

        <details className="profile-group">
          <summary>Publications ({profile.publications.length})</summary>
          {profile.publications.map((item, index) => (
            <div className="profile-item" key={item.id}>
              <label className="profile-field"><span>Publication title</span><input value={item.title} onChange={(event) => updateItem('publications', index, { title: event.target.value })} required /></label>
              <label className="profile-field"><span>Venue</span><input value={item.venue ?? ''} onChange={(event) => updateItem('publications', index, { venue: event.target.value })} /></label>
              <label className="profile-field"><span>Year</span><input type="number" min="1900" max="2100" value={item.year ?? ''} onChange={(event) => updateItem('publications', index, { year: optionalYear(event.target.value) })} /></label>
              <label className="profile-field"><span>URL</span><input type="url" value={item.url ?? ''} onChange={(event) => updateItem('publications', index, { url: event.target.value || null })} /></label>
              <EvidenceDocuments documents={documents} value={item.document_ids} onChange={(document_ids) => updateItem('publications', index, { document_ids })} />
              <button className="ghost remove-item" type="button" onClick={() => removeItem('publications', index)}>Remove publication</button>
            </div>
          ))}
          <button className="ghost" type="button" onClick={() => addItem('publications', { id: itemId('publication'), title: '', document_ids: [] })}>Add publication</button>
        </details>

        <div className="profile-save">
          <button type="submit" disabled={loading || saving}>{saving ? 'Saving profile...' : 'Save candidate profile'}</button>
          <p className="analysis-status" aria-live="polite">{status}</p>
        </div>
      </form>
    </section>
  )
}
