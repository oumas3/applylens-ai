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
    'Upload a PDF and send it to the API.'
  )
  const [uploadedDocument, setUploadedDocument] = useState<{
    filename: string
    size_bytes: number
  } | null>(null)

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

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!selectedFile) {
      setUploadStatus('Select a PDF file before uploading.')
      return
    }

    setUploading(true)
    setUploadStatus('Uploading document...')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch(`${API_URL}/api/v1/documents`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail ?? 'Upload failed.')
      }

      const payload = await response.json()
      setUploadedDocument({
        filename: payload.filename,
        size_bytes: payload.size_bytes,
      })
      setUploadStatus(`Uploaded ${payload.filename}`)
      setSelectedFile(null)
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : 'Upload failed unexpectedly.'
      )
    } finally {
      setUploading(false)
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
            <h3>Send your first PDF</h3>
            <label className="upload-field">
              <span>Choose a PDF</span>
              <input
                type="file"
                accept="application/pdf"
                onChange={(event) =>
                  setSelectedFile(event.target.files?.[0] ?? null)
                }
              />
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
            {uploadedDocument ? (
              <p className="upload-meta">
                Stored as {uploadedDocument.filename} •{' '}
                {uploadedDocument.size_bytes} bytes
              </p>
            ) : null}
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