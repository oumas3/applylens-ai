import { useEffect, useState, type FormEvent } from 'react'

const API_URL =
  import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

type AnalysisResult = {
  title: string
  institution?: string | null
  degree_type?: string | null
  eligibility: string
  matched_requirements: string[]
  missing_requirements: string[]
  evidence_summary: string[]
  requirement_results: RequirementResult[]
  deadline?: string | null
  deadline_date?: string | null
  funding?: string | null
  funding_status?: 'available' | 'unavailable' | 'unclear'
  application_url?: string | null
  required_documents?: string[]
}

type RequirementResult = {
  requirement: string
  status: string
  evidence: string[]
  explanation: string
  action?: string | null
}

type IngestedOpportunity = {
  id: string
  title: string
  source_text: string
  institution?: string | null
  degree_type?: string | null
  source_name?: string | null
  source_url?: string | null
  requirements: string[]
  deadline?: string | null
  deadline_date?: string | null
  funding?: string | null
  requirement_citations: Array<{
    requirement: string
    source_name?: string | null
    page?: number | null
  }>
}

type RetrievalResult = {
  chunk: {
    chunk_id: string
    text: string
    source_name?: string | null
    page?: number | null
    index: number
  }
  score: number
}

type TaskItem = {
  id: number
  opportunity_id?: string | null
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

type ReviewComparison = {
  reviews: OpportunityReview[]
  recommended_review_id: number | null
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
  const [analysisInstitution, setAnalysisInstitution] = useState('Example University')
  const [analysisDegreeType, setAnalysisDegreeType] = useState('PhD')
  const [analysisApplicationUrl, setAnalysisApplicationUrl] = useState('')
  const [analysisRequiredDocuments, setAnalysisRequiredDocuments] = useState('CV\nTranscript')
  const [analysisRequirements, setAnalysisRequirements] = useState(
    "Bachelor's degree\nResearch experience\nEnglish proficiency"
  )
  const [analysisEvidence, setAnalysisEvidence] = useState(
    "Bachelor's degree completed\nPublished two papers"
  )
  const [analysisDeadline, setAnalysisDeadline] = useState('')
  const [analysisDeadlineDate, setAnalysisDeadlineDate] = useState('')
  const [analysisFunding, setAnalysisFunding] = useState('')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisStatus, setAnalysisStatus] = useState(
    'Add an opportunity title, requirements, and evidence to review it.'
  )
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [opportunityFile, setOpportunityFile] = useState<File | null>(null)
  const [opportunityTitle, setOpportunityTitle] = useState('')
  const [opportunityLoading, setOpportunityLoading] = useState(false)
  const [opportunityStatus, setOpportunityStatus] = useState(
    'Upload an academic call to extract its requirements.'
  )
  const [ingestedOpportunity, setIngestedOpportunity] =
    useState<IngestedOpportunity | null>(null)
  const [ingestedOpportunities, setIngestedOpportunities] = useState<
    IngestedOpportunity[]
  >([])
  const [ingestedOpportunitiesLoading, setIngestedOpportunitiesLoading] =
    useState(false)
  const [retrievalQuery, setRetrievalQuery] = useState('')
  const [retrievalResults, setRetrievalResults] = useState<RetrievalResult[]>([])
  const [retrievalLoading, setRetrievalLoading] = useState(false)
  const [retrievalSearched, setRetrievalSearched] = useState(false)
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [reviews, setReviews] = useState<OpportunityReview[]>([])
  const [reviewsLoading, setReviewsLoading] = useState(false)
  const [selectedReviewIds, setSelectedReviewIds] = useState<number[]>([])
  const [comparison, setComparison] = useState<ReviewComparison | null>(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)

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

  async function handleTaskStatusChange(taskId: number, status: string) {
    try {
      const response = await fetch(`${API_URL}/api/v1/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })

      if (!response.ok) {
        throw new Error('Unable to update task status.')
      }

      const updatedTask: TaskItem = await response.json()
      setTasks((current) =>
        current.map((task) => (task.id === updatedTask.id ? updatedTask : task))
      )
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : 'Unable to update task status.'
      )
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

  async function loadIngestedOpportunities() {
    setIngestedOpportunitiesLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/v1/opportunities/ingested`)
      if (!response.ok) {
        throw new Error('Unable to load saved opportunities.')
      }
      setIngestedOpportunities(await response.json())
    } catch (error) {
      setOpportunityStatus(
        error instanceof Error
          ? error.message
          : 'Unable to load saved opportunities.'
      )
    } finally {
      setIngestedOpportunitiesLoading(false)
    }
  }

  useEffect(() => {
    void loadIngestedOpportunities()
  }, [])

  async function compareSelectedReviews() {
    if (selectedReviewIds.length < 2) {
      setUploadStatus('Select at least two saved reviews to compare.')
      return
    }

    setComparisonLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/v1/reviews/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_ids: selectedReviewIds }),
      })

      if (!response.ok) {
        throw new Error('Unable to compare saved reviews.')
      }

      setComparison(await response.json())
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : 'Unable to compare saved reviews.'
      )
      setComparison(null)
    } finally {
      setComparisonLoading(false)
    }
  }

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

  async function handleOpportunityIngest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!opportunityFile || !opportunityTitle.trim()) {
      setOpportunityStatus('Add an opportunity title and select a PDF or TXT call.')
      return
    }

    setOpportunityLoading(true)
    setOpportunityStatus('Extracting opportunity requirements...')

    try {
      const formData = new FormData()
      formData.append('file', opportunityFile)
      formData.append('title', opportunityTitle.trim())

      const response = await fetch(`${API_URL}/api/v1/opportunities/ingest-file`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail ?? 'Unable to ingest the opportunity.')
      }

      const payload: IngestedOpportunity = await response.json()
      setIngestedOpportunity(payload)
      setIngestedOpportunities((current) => [payload, ...current])
      setOpportunityStatus(
        `Extracted ${payload.requirements.length} requirement(s) from ${payload.source_name ?? 'the call'}.`
      )
      setOpportunityFile(null)
    } catch (error) {
      setOpportunityStatus(
        error instanceof Error ? error.message : 'Unable to ingest the opportunity.'
      )
    } finally {
      setOpportunityLoading(false)
    }
  }

  function useIngestedOpportunity() {
    if (!ingestedOpportunity) {
      return
    }

    setAnalysisTitle(ingestedOpportunity.title)
    setAnalysisInstitution(ingestedOpportunity.institution ?? '')
    setAnalysisDegreeType(ingestedOpportunity.degree_type ?? '')
    setAnalysisRequirements(ingestedOpportunity.requirements.join('\n'))
    setAnalysisApplicationUrl(ingestedOpportunity.source_url ?? '')
    setAnalysisDeadline(ingestedOpportunity.deadline ?? '')
    setAnalysisDeadlineDate(ingestedOpportunity.deadline_date ?? '')
    setAnalysisFunding(ingestedOpportunity.funding ?? '')
    setRetrievalResults([])
    setRetrievalQuery('')
    setRetrievalSearched(false)
    setAnalysisStatus('Opportunity details loaded. Add evidence and analyse it.')
    document.getElementById('opportunity-analysis-form')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  }

  function selectSavedOpportunity(opportunity: IngestedOpportunity) {
    setIngestedOpportunity(opportunity)
    setOpportunityTitle(opportunity.title)
    setAnalysisTitle(opportunity.title)
    setAnalysisInstitution(opportunity.institution ?? '')
    setAnalysisDegreeType(opportunity.degree_type ?? '')
    setAnalysisRequirements(opportunity.requirements.join('\n'))
    setAnalysisApplicationUrl(opportunity.source_url ?? '')
    setAnalysisDeadline(opportunity.deadline ?? '')
    setAnalysisDeadlineDate(opportunity.deadline_date ?? '')
    setAnalysisFunding(opportunity.funding ?? '')
    setRetrievalResults([])
    setRetrievalQuery('')
    setRetrievalSearched(false)
    setAnalysisStatus('Saved opportunity loaded. Add evidence and analyse it.')
  }

  function useRetrievalResultsAsEvidence() {
    if (retrievalResults.length === 0) {
      return
    }

    setAnalysisEvidence((current) => {
      const existing = current
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean)
      const additions = retrievalResults.map((result) => {
        const source = result.chunk.source_name ?? 'opportunity source'
        const page = result.chunk.page ? `, page ${result.chunk.page}` : ''
        return `${result.chunk.text} [Source: ${source}${page}]`
      })
      return Array.from(new Set([...existing, ...additions])).join('\n')
    })
    setAnalysisStatus('Search results added to evidence. Review them before analysing.')
    document.getElementById('opportunity-analysis-form')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  }

  async function deleteSavedOpportunity(opportunityId: string) {
    try {
      const response = await fetch(
        `${API_URL}/api/v1/opportunities/ingested/${opportunityId}`,
        { method: 'DELETE' }
      )

      if (!response.ok) {
        throw new Error('Unable to delete saved opportunity.')
      }

      setIngestedOpportunities((current) =>
        current.filter((opportunity) => opportunity.id !== opportunityId)
      )
      if (ingestedOpportunity?.id === opportunityId) {
        setIngestedOpportunity(null)
      }
      setOpportunityStatus('Saved opportunity deleted.')
    } catch (error) {
      setOpportunityStatus(
        error instanceof Error
          ? error.message
          : 'Unable to delete saved opportunity.'
      )
    }
  }

  async function searchOpportunityEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ingestedOpportunity || !retrievalQuery.trim()) {
      setOpportunityStatus('Select an opportunity and enter a search question.')
      return
    }

    setRetrievalLoading(true)
    try {
      const response = await fetch(
        `${API_URL}/api/v1/opportunities/ingested/${ingestedOpportunity.id}/evidence-search`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: retrievalQuery.trim(), top_k: 5 }),
        }
      )
      if (!response.ok) {
        throw new Error('Unable to search opportunity evidence.')
      }
      setRetrievalResults(await response.json())
      setRetrievalSearched(true)
    } catch (error) {
      setOpportunityStatus(
        error instanceof Error
          ? error.message
          : 'Unable to search opportunity evidence.'
      )
      setRetrievalResults([])
      setRetrievalSearched(false)
    } finally {
      setRetrievalLoading(false)
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
          institution: analysisInstitution.trim() || null,
          degree_type: analysisDegreeType.trim() || null,
          requirements,
          evidence,
          document_ids: documents.map((document) => document.id),
          application_url: analysisApplicationUrl.trim() || null,
          required_documents: analysisRequiredDocuments
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean),
          deadline: analysisDeadline.trim() || null,
          deadline_date: analysisDeadlineDate || null,
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

      const tasksResponse = await fetch(`${API_URL}/api/v1/tasks/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          opportunity_id: ingestedOpportunity?.id ?? null,
          missing_requirements: payload.missing_requirements,
          deadline: payload.deadline ?? null,
          funding: payload.funding ?? null,
        }),
      })

      if (tasksResponse.ok) {
        const generatedTasks: TaskItem[] = await tasksResponse.json()
        setTasks(generatedTasks)
      }

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

          <form className="upload-card" onSubmit={handleOpportunityIngest}>
            <p className="eyebrow">OPPORTUNITY INGESTION</p>
            <h3>Extract an academic call</h3>
            <label className="upload-field">
              <span>Opportunity title</span>
              <input
                value={opportunityTitle}
                onChange={(event) => setOpportunityTitle(event.target.value)}
                placeholder="PhD in Artificial Intelligence"
              />
            </label>
            <label className="upload-field">
              <span>Academic call PDF or TXT</span>
              <input
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                onChange={(event) =>
                  setOpportunityFile(event.target.files?.[0] ?? null)
                }
              />
            </label>
            <button type="submit" disabled={opportunityLoading || !opportunityFile}>
              {opportunityLoading ? 'Extracting...' : 'Extract opportunity'}
            </button>
            <p className="upload-status">{opportunityStatus}</p>

            {ingestedOpportunity && (
              <section className="text-preview" aria-live="polite">
                <p className="eyebrow">OPPORTUNITY DETAILS</p>
                <h3>{ingestedOpportunity.title}</h3>
                <div className="analysis-meta">
                  <div>
                    <h4>Institution</h4>
                    <p>{ingestedOpportunity.institution || 'Not provided'}</p>
                  </div>
                  <div>
                    <h4>Degree type</h4>
                    <p>{ingestedOpportunity.degree_type || 'Not provided'}</p>
                  </div>
                  <div>
                    <h4>Source</h4>
                    <p>{ingestedOpportunity.source_name || 'Pasted text'}</p>
                  </div>
                </div>
                <details>
                  <summary>View full source text</summary>
                  <pre>{ingestedOpportunity.source_text}</pre>
                </details>
                <h4>Extracted requirements and citations</h4>
                {ingestedOpportunity.requirements.length === 0 ? (
                  <p className="upload-status">No requirement lines were detected.</p>
                ) : (
                  <ul>
                    {ingestedOpportunity.requirement_citations.map((citation) => (
                      <li key={`${citation.requirement}-${citation.page ?? 'text'}`}>
                        <strong>{citation.requirement}</strong>
                        <p>
                          Source: {citation.source_name ?? 'pasted text'}
                          {citation.page ? `, page ${citation.page}` : ''}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
                <button type="button" onClick={useIngestedOpportunity}>
                  Use for analysis
                </button>
                <form onSubmit={searchOpportunityEvidence}>
                  <label className="upload-field">
                    <span>Search source evidence</span>
                    <input
                      value={retrievalQuery}
                      onChange={(event) => setRetrievalQuery(event.target.value)}
                      placeholder="What English proficiency evidence is required?"
                    />
                  </label>
                  <button type="submit" disabled={retrievalLoading}>
                    {retrievalLoading ? 'Searching...' : 'Search evidence'}
                  </button>
                </form>
                {retrievalResults.length > 0 && (
                  <>
                    <button type="button" onClick={useRetrievalResultsAsEvidence}>
                      Use results as evidence
                    </button>
                    <ul>
                      {retrievalResults.map((result) => (
                        <li key={result.chunk.chunk_id}>
                          <strong>{(result.score * 100).toFixed(1)}% match</strong>
                          <p>{result.chunk.text}</p>
                          <p>
                            Source: {result.chunk.source_name ?? 'Unknown'}
                            {result.chunk.page ? `, page ${result.chunk.page}` : ''}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {retrievalSearched && retrievalResults.length === 0 && !retrievalLoading && (
                  <p className="upload-status">
                    No matching evidence was found in this opportunity source.
                  </p>
                )}
              </section>
            )}

            <section className="document-list">
              <p className="eyebrow">SAVED OPPORTUNITIES</p>
              {ingestedOpportunitiesLoading ? (
                <p className="upload-meta">Loading saved opportunities...</p>
              ) : ingestedOpportunities.length === 0 ? (
                <p className="upload-status">No saved opportunities yet.</p>
              ) : (
                ingestedOpportunities.map((opportunity) => (
                  <article className="document-item" key={opportunity.id}>
                    <div>
                      <strong>{opportunity.title}</strong>
                      <p>
                        {opportunity.requirements.length} requirement(s)
                        {opportunity.source_name
                          ? ` • ${opportunity.source_name}`
                          : ''}
                      </p>
                    </div>
                    <div className="document-actions">
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => selectSavedOpportunity(opportunity)}
                      >
                        Select
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => void deleteSavedOpportunity(opportunity.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </article>
                ))
              )}
            </section>
          </form>

          <form
            className="analysis-form"
            id="opportunity-analysis-form"
            onSubmit={handleAnalyseOpportunity}
          >
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
              <span>Institution</span>
              <input
                value={analysisInstitution}
                onChange={(event) => setAnalysisInstitution(event.target.value)}
                placeholder="Example University"
              />
            </label>

            <label className="upload-field">
              <span>Degree type</span>
              <input
                value={analysisDegreeType}
                onChange={(event) => setAnalysisDegreeType(event.target.value)}
                placeholder="PhD"
              />
            </label>

            <label className="upload-field">
              <span>Deadline date</span>
              <input
                type="date"
                value={analysisDeadlineDate}
                onChange={(event) => setAnalysisDeadlineDate(event.target.value)}
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

            <label className="upload-field">
              <span>Application URL</span>
              <input
                type="url"
                value={analysisApplicationUrl}
                onChange={(event) => setAnalysisApplicationUrl(event.target.value)}
                placeholder="https://example.edu/apply"
              />
            </label>

            <label className="upload-field">
              <span>Required documents (one per line)</span>
              <textarea
                value={analysisRequiredDocuments}
                onChange={(event) => setAnalysisRequiredDocuments(event.target.value)}
                rows={3}
                placeholder="CV\nTranscript"
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
                  setAnalysisInstitution('')
                  setAnalysisDegreeType('')
                  setAnalysisApplicationUrl('')
                  setAnalysisRequiredDocuments('')
                  setAnalysisRequirements('')
                  setAnalysisEvidence('')
                  setAnalysisDeadline('')
                  setAnalysisDeadlineDate('')
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

              <div className="analysis-requirements">
                <h4>Requirement review</h4>
                {analysisResult.requirement_results.map((result) => (
                  <article className="requirement-result" key={result.requirement}>
                    <div className="analysis-result-header">
                      <strong>{result.requirement}</strong>
                      <span
                        className={`analysis-pill ${result.status
                          .toLowerCase()
                          .replaceAll(' ', '-')}`}
                      >
                        {result.status}
                      </span>
                    </div>
                    <p>{result.explanation}</p>
                    {result.evidence.length > 0 && (
                      <ul>
                        {result.evidence.map((evidence) => (
                          <li key={evidence}>{evidence}</li>
                        ))}
                      </ul>
                    )}
                    {result.action && <p><strong>Next action:</strong> {result.action}</p>}
                  </article>
                ))}
              </div>

              <div className="analysis-evidence">
                <div className="analysis-meta">
                  <div>
                    <h4>Institution</h4>
                    <p>{analysisResult.institution || 'Not provided'}</p>
                  </div>
                  <div>
                    <h4>Degree type</h4>
                    <p>{analysisResult.degree_type || 'Not provided'}</p>
                  </div>
                  <div>
                    <h4>Application</h4>
                    <p>{analysisResult.application_url || 'Not provided'}</p>
                  </div>
                </div>
                <h4>Evidence summary</h4>
                <ul>
                  {analysisResult.evidence_summary.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              {analysisResult.required_documents?.length ? (
                <div className="analysis-evidence">
                  <h4>Required documents</h4>
                  <ul>
                    {analysisResult.required_documents.map((document) => (
                      <li key={document}>{document}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="analysis-meta">
                <div>
                  <h4>Deadline</h4>
                  <p>
                    {analysisResult.deadline || 'Not provided'}
                    {analysisResult.deadline_date && ` (${analysisResult.deadline_date})`}
                  </p>
                </div>
                <div>
                  <h4>Funding</h4>
                  <p>{analysisResult.funding || 'Not provided'}</p>
                  <p>Status: {analysisResult.funding_status || 'unclear'}</p>
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
                  <select
                    value={task.status}
                    aria-label={`Status for ${task.title}`}
                    onChange={(event) =>
                      void handleTaskStatusChange(task.id, event.target.value)
                    }
                  >
                    <option value="pending">Pending</option>
                    <option value="in_progress">In progress</option>
                    <option value="completed">Completed</option>
                  </select>
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
            <>
              <div className="actions">
                <button
                  type="button"
                  onClick={() => void compareSelectedReviews()}
                  disabled={comparisonLoading || selectedReviewIds.length < 2}
                >
                  {comparisonLoading ? 'Comparing...' : 'Compare selected'}
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setSelectedReviewIds([])
                    setComparison(null)
                  }}
                >
                  Clear comparison
                </button>
              </div>

              <ul className="task-list">
              {reviews.map((review) => (
                <li key={review.id} className="review-item">
                  <input
                    type="checkbox"
                    checked={selectedReviewIds.includes(review.id)}
                    aria-label={`Select ${review.title} for comparison`}
                    onChange={() =>
                      setSelectedReviewIds((current) =>
                        current.includes(review.id)
                          ? current.filter((id) => id !== review.id)
                          : [...current, review.id]
                      )
                    }
                  />
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
              {comparison && (
                <p className="analysis-status">
                  Recommended: {
                    comparison.reviews.find(
                      (review) => review.id === comparison.recommended_review_id
                    )?.title ?? 'No recommendation'
                  }
                </p>
              )}
            </>
          )}
        </div>

        <div className="stats">
          <article>
            <strong>{ingestedOpportunities.length}</strong>
            <span>Opportunities</span>
          </article>
          <article>
            <strong>
              {ingestedOpportunities.filter(
                (opportunity) => opportunity.deadline || opportunity.deadline_date
              ).length}
            </strong>
            <span>Deadline tracked</span>
          </article>
          <article>
            <strong>{analysisResult ? 1 : 0}</strong>
            <span>Calls analysed</span>
          </article>
        </div>

        <div className="grid">
          {ingestedOpportunities.length === 0 ? (
            <p className="upload-status">
              No saved opportunities yet. Extract an academic call above to start your workspace.
            </p>
          ) : ingestedOpportunities.map((opportunity) => (
            <article className="opportunity" key={opportunity.id}>
              <span className="tag">{opportunity.degree_type ?? 'Opportunity'}</span>
              <h3>{opportunity.title}</h3>
              <p>{opportunity.institution ?? 'Institution not provided'}</p>
              <footer>
                <span>
                  {ingestedOpportunity?.id === opportunity.id
                    ? 'Selected'
                    : 'Ready to analyse'}
                </span>
                <button
                  type="button"
                  aria-label={`Open ${opportunity.title}`}
                  onClick={() => selectSavedOpportunity(opportunity)}
                >→</button>
              </footer>
            </article>
          ))}
        </div>
      </section>

      <footer className="page-footer">
        Built by Oumaima Ouayres • Sprint 6 • Master's and PhD MVP
      </footer>
    </main>
  )
}
