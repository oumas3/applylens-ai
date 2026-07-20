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
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => void handleDelete(document.id)}
                    >
                      Delete
                    </button>
                  </article>
                ))
              )}
            </div>
          </form>
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