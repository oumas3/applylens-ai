import { useEffect, useState, type FormEvent } from 'react'

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

type AnalysisResult = {
  title: string
  eligibility: string
  matched_requirements: string[]
  missing_requirements: string[]
  evidence_summary: string[]
  deadline?: string | null
  funding?: string | null
}

type TaskItem = {
  id: number
  title: string
  status: string
}

type OpportunityReview = {
  id: number
  title: string
  eligibility: string
  matched_requirements?: string[]
  missing_requirements?: string[]
  deadline?: string | null
  funding?: string | null
}

export default function App() {
  const [apiStatus, setApiStatus] = useState('CONNECTING TO API...')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState(
    'Upload a PDF or TXT document and send it to the API.'
  )
  const [documents, setDocuments] = useState<
    Array<{
      id: string
      original_filename: string
      stored_filename: string
      category: string
      content_type: string
      size_bytes: number
      status: string
      extracted_text_length: number
      uploaded_at: string
    }>
  >([])
  const [documentsLoading, setDocumentsLoading] = useState(false)
  const [documentCategory, setDocumentCategory] = useState('OTHER')
  const [previewText, setPreviewText] = useState('')
  const [previewTitle, setPreviewTitle] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [analysisTitle, setAnalysisTitle] = useState('PhD in AI')
  const [analysisRequirements, setAnalysisRequirements] = useState(
    "Bachelor's degree\nResearch experience\nEnglish proficiency"
  )
  const [analysisEvidence, setAnalysisEvidence] = useState(
    "Bachelor's degree completed\nPublished two papers"
  )
  const [analysisDeadline, setAnalysisDeadline] = useState('24 July 2026')
  const [analysisFunding, setAnalysisFunding] = useState('Scholarship available')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisStatus, setAnalysisStatus] = useState(
    'Add an opportunity title, requirements, and evidence to review it.'
  )
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [reviews, setReviews] = useState<OpportunityReview[]>([])
  const [reviewsLoading, setReviewsLoading] = useState(false)

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

  async function loadDocuments() {
    setDocumentsLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/v1/documents`)

      if (!response.ok) {
        throw new Error('Unable to load documents.')
      }

      const payload = await response.json()
      setDocuments(payload)
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : 'Unable to load documents.'
      )
    } finally {
      setDocumentsLoading(false)
    }
  }

  useEffect(() => {
    void loadDocuments()
  }, [])

  async function loadTasks() {
    setTasksLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/v1/tasks`)

      if (!response.ok) {
        throw new Error('Unable to load tasks.')
      }

      const payload = await response.json()
      setTasks(payload)
    } catch (error) {
      setTasks([])
    } finally {
      setTasksLoading(false)
    }
  }

  useEffect(() => {
    void loadTasks()
  }, [])

  async function loadReviews() {
    setReviewsLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/v1/reviews`)

      if (!response.ok) {
        throw new Error('Unable to load reviews.')
      }

      const payload = await response.json()
      setReviews(payload)
    } catch (error) {
      setReviews([])
    } finally {
      setReviewsLoading(false)
    }
  }

  useEffect(() => {
    void loadReviews()
  }, [])

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!selectedFile) {
      setUploadStatus('Select a PDF or TXT file before uploading.')
      return
    }

    setUploading(true)
    setUploadStatus('Uploading document...')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch(
        `${API_URL}/api/v1/documents?category=${encodeURIComponent(documentCategory)}`,
        {
          method: 'POST',
          body: formData,
        }
      )

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail ?? 'Upload failed.')
      }

      const payload = await response.json()
      setDocuments((current) => [payload, ...current])
      setUploadStatus(
        `Uploaded ${payload.original_filename} (${payload.extracted_text_length} chars extracted)`
      )
      setSelectedFile(null)
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : 'Upload failed unexpectedly.'
      )
    } finally {
      setUploading(false)
    }
  }
async function handlePreviewText(
  documentId: string,
  filename: string
) {
  setPreviewLoading(true)
  setPreviewTitle(filename)
  setPreviewText('')

  try {
    const response = await fetch(
      `${API_URL}/api/v1/documents/${documentId}/text`
    )

    if (!response.ok) {
      throw new Error('Unable to load the extracted text.')
    }

    const text = await response.text()
    setPreviewText(text || 'No readable text was found in this document.')
  } catch (error) {
    setPreviewText(
      error instanceof Error
        ? error.message
        : 'Unable to load the extracted text.'
    )
  } finally {
    setPreviewLoading(false)
  }
}
  async function handleDelete(documentId: string) {
    try {
      const response = await fetch(`${API_URL}/api/v1/documents/${documentId}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        throw new Error('Unable to delete document.')
      }

      setDocuments((current) => current.filter((item) => item.id !== documentId))
      setUploadStatus('Document removed.')
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : 'Unable to delete document.'
      )
    }
  }

  async function handleAnalyseOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    setAnalysisLoading(true)
    setAnalysisStatus('Analyzing opportunity...')

    try {
      const requirements = analysisRequirements
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean)
      const evidence = analysisEvidence
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean)

      const response = await fetch(`${API_URL}/api/v1/opportunities/analyse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: analysisTitle.trim(),
          requirements,
          evidence,
          deadline: analysisDeadline.trim() || null,
          funding: analysisFunding.trim() || null,
        }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail ?? 'Unable to analyze the opportunity.')
      }

      const payload: AnalysisResult = await response.json()
      setAnalysisResult(payload)
      setAnalysisStatus(`Review ready for ${payload.title}.`)

      const reviewPayload: OpportunityReview = {
        id: Date.now(),
        title: payload.title,
        eligibility: payload.eligibility,
        matched_requirements: payload.matched_requirements,
        missing_requirements: payload.missing_requirements,
        deadline: payload.deadline ?? null,
        funding: payload.funding ?? null,
      }

      await fetch(`${API_URL}/api/v1/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reviewPayload),
      })

      setReviews((current) => [reviewPayload, ...current])
    } catch (error) {
      setAnalysisResult(null)
      setAnalysisStatus(
        error instanceof Error ? error.message : 'Unable to analyze the opportunity.'
      )
    } finally {
      setAnalysisLoading(false)
    }
  }

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
            <button
              type="button"
              onClick={() =>
                document.getElementById('opportunity-analysis')?.scrollIntoView({
                  behavior: 'smooth',
                  block: 'start',
                })
              }
            >
              Analyse an opportunity
            </button>
            <button className="ghost">Build my profile</button>
          </div>

          <form className="upload-card" onSubmit={handleUpload}>
            <p className="eyebrow">DOCUMENT UPLOAD</p>
            <h3>Send your first PDF or TXT</h3>
            <label className="upload-field">
              <span>Choose a PDF or TXT</span>
              <input
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                onChange={(event) =>
                  setSelectedFile(event.target.files?.[0] ?? null)
                }
              />
            </label>
            <label className="upload-field">
              <span>Document category</span>
              <select
                value={documentCategory}
                onChange={(event) => setDocumentCategory(event.target.value)}
              >
                <option value="CV">CV</option>
                <option value="COVER_LETTER">Cover letter</option>
                <option value="TRANSCRIPT">Transcript</option>
                <option value="MOTIVATION_LETTER">Motivation letter</option>
                <option value="OTHER">Other</option>
              </select>
            </label>
            <div className="actions">
              <button type="submit" disabled={uploading || !selectedFile}>
                {uploading ? 'Uploading...' : 'Upload document'}
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => setSelectedFile(null)}
              >
                Clear
              </button>
            </div>
            <p className="upload-status">{uploadStatus}</p>
            <div className="document-list">
              <p className="eyebrow">UPLOADED DOCUMENTS</p>
              {documentsLoading ? (
                <p className="upload-meta">Loading documents...</p>
              ) : documents.length === 0 ? (
                <p className="upload-status">
                  No documents uploaded yet.
                </p>
              ) : (
                documents.map((document) => (
                  <article className="document-item" key={document.id}>
                    <div>
                      <strong>{document.original_filename}</strong>
                      <p>
                        {document.category} • {document.content_type} •{' '}
                        {document.size_bytes} bytes • {document.extracted_text_length}{' '}
                        chars extracted
                      </p>
                    </div>
                    <div className="document-actions">
  <button type="button" className="ghost" onClick={() => void handlePreviewText(document.id, document.original_filename)}>View text</button>
  <button type="button" className="ghost" onClick={() => void handleDelete(document.id)}>Delete</button>
</div>
                  </article>
                ))
              )}
            </div>
              {previewTitle && (
  <section className="text-preview" aria-live="polite">
    <div className="text-preview-header">
      <div>
        <p className="eyebrow">EXTRACTED TEXT</p>
        <h3>{previewTitle}</h3>
      </div>

      <button
        type="button"
        className="ghost"
        onClick={() => {
          setPreviewTitle('')
          setPreviewText('')
        }}
      >
        Close
      </button>
    </div>

    <pre>
      {previewLoading
        ? 'Loading extracted text...'
        : previewText}
    </pre>
  </section>
)}
          </form>
        </div>

        <div className="decision-card" id="opportunity-analysis">
          <p className="muted">ELIGIBILITY PREVIEW</p>
          <h2>Evidence, not guesses</h2>

          <form className="analysis-form" onSubmit={handleAnalyseOpportunity}>
            <label className="upload-field">
              <span>Opportunity title</span>
              <input
                value={analysisTitle}
                onChange={(event) => setAnalysisTitle(event.target.value)}
                placeholder="PhD in AI"
              />
            </label>

            <label className="upload-field">
              <span>Requirements (one per line)</span>
              <textarea
                value={analysisRequirements}
                onChange={(event) => setAnalysisRequirements(event.target.value)}
                rows={5}
                placeholder="Bachelor's degree\nResearch experience"
              />
            </label>

            <label className="upload-field">
              <span>Evidence (one per line)</span>
              <textarea
                value={analysisEvidence}
                onChange={(event) => setAnalysisEvidence(event.target.value)}
                rows={5}
                placeholder="Bachelor's degree completed\nPublished two papers"
              />
            </label>

            <label className="upload-field">
              <span>Deadline</span>
              <input
                value={analysisDeadline}
                onChange={(event) => setAnalysisDeadline(event.target.value)}
                placeholder="24 July 2026"
              />
            </label>

            <label className="upload-field">
              <span>Funding note</span>
              <input
                value={analysisFunding}
                onChange={(event) => setAnalysisFunding(event.target.value)}
                placeholder="Scholarship available"
              />
            </label>

            <div className="actions">
              <button type="submit" disabled={analysisLoading}>
                {analysisLoading ? 'Analyzing...' : 'Analyse opportunity'}
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setAnalysisTitle('')
                  setAnalysisRequirements('')
                  setAnalysisEvidence('')
                  setAnalysisDeadline('')
                  setAnalysisFunding('')
                  setAnalysisResult(null)
                  setAnalysisStatus(
                    'Add an opportunity title, requirements, and evidence to review it.'
                  )
                }}
              >
                Reset
              </button>
            </div>
          </form>

          <p className="analysis-status">{analysisStatus}</p>

          {analysisResult && (
            <section className="analysis-result" aria-live="polite">
              <div className="analysis-result-header">
                <div>
                  <p className="eyebrow">RESULT</p>
                  <h3>{analysisResult.title}</h3>
                </div>
                <span className={`analysis-pill ${analysisResult.eligibility.toLowerCase()}`}>
                  {analysisResult.eligibility}
                </span>
              </div>

              <div className="analysis-grid">
                <div>
                  <h4>Matched requirements</h4>
                  <ul>
                    {analysisResult.matched_requirements.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div>
                  <h4>Missing requirements</h4>
                  <ul>
                    {analysisResult.missing_requirements.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="analysis-evidence">
                <h4>Evidence summary</h4>
                <ul>
                  {analysisResult.evidence_summary.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="analysis-meta">
                <div>
                  <h4>Deadline</h4>
                  <p>{analysisResult.deadline || 'Not provided'}</p>
                </div>
                <div>
                  <h4>Funding</h4>
                  <p>{analysisResult.funding || 'Not provided'}</p>
                </div>
              </div>
            </section>
          )}
        </div>
      </section>

      <section className="workspace">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h2>Applications at a glance</h2>
        </div>

        <div className="task-card">
          <div className="task-card-header">
            <div>
              <p className="eyebrow">APPLICATION TASKS</p>
              <h3>Next actions for this opportunity</h3>
            </div>
            <span className="task-count">{tasks.length} tasks</span>
          </div>

          {tasksLoading ? (
            <p className="upload-status">Loading tasks...</p>
          ) : (
            <ul className="task-list">
              {tasks.map((task) => (
                <li key={task.id}>
                  <span>{task.title}</span>
                  <strong>{task.status}</strong>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="task-card">
          <div className="task-card-header">
            <div>
              <p className="eyebrow">SAVED REVIEWS</p>
              <h3>Recent opportunity analyses</h3>
            </div>
            <span className="task-count">{reviews.length} saved</span>
          </div>

          {reviewsLoading ? (
            <p className="upload-status">Loading reviews...</p>
          ) : reviews.length === 0 ? (
            <p className="upload-status">No saved reviews yet.</p>
          ) : (
            <ul className="task-list">
              {reviews.map((review) => (
                <li key={review.id} className="review-item">
                  <div>
                    <span>{review.title}</span>
                    <p>
                      {review.matched_requirements?.length ? `Matched: ${review.matched_requirements.join(', ')}` : 'No matched requirements'}
                    </p>
                    <p>
                      {review.missing_requirements?.length ? `Missing: ${review.missing_requirements.join(', ')}` : 'No missing requirements'}
                    </p>
                  </div>
                  <strong>{review.eligibility}</strong>
                </li>
              ))}
            </ul>
          )}
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
            <strong>{analysisResult ? 1 : 0}</strong>
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
        Built by Oumaima Ouayres • Sprint 2 • Master's and PhD MVP
      </footer>
    </main>
  )
}