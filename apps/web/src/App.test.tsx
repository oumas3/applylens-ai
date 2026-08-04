import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

type MockResponse = {
  ok: boolean
  status: number
  json: () => Promise<unknown>
  text: () => Promise<string>
}

function responseFor(payload: unknown, status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
    text: async () => (typeof payload === 'string' ? payload : JSON.stringify(payload)),
  }
}

function defaultFetchResponse(url: string, method: string): MockResponse {
  if (url.endsWith('/health')) {
    return responseFor({ status: 'ok' })
  }
  if (url.endsWith('/api/v1/documents')) {
    return responseFor([])
  }
  if (url.endsWith('/api/v1/tasks')) {
    return responseFor([])
  }
  if (url.endsWith('/api/v1/reviews')) {
    return responseFor(method === 'POST' ? {} : [])
  }
  if (url.endsWith('/api/v1/opportunities/ingested')) {
    return responseFor([])
  }
  return responseFor({})
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ApplyLens UI', () => {
  it('renders the connected empty workspace', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        Promise.resolve(defaultFetchResponse(String(input), init?.method ?? 'GET'))
      )
    )

    render(<App />)

    expect(screen.getByRole('heading', { name: /Know where you qualify/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/API CONNECTED/)).toBeInTheDocument())
    expect(screen.getByText('No documents uploaded yet.')).toBeInTheDocument()
    expect(screen.getByText('No saved opportunities yet.')).toBeInTheDocument()
  })

  it('shows an offline status when the API health check fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).endsWith('/health')) {
          return Promise.resolve(responseFor({ detail: 'offline' }, 503))
        }
        return Promise.resolve(defaultFetchResponse(String(input), 'GET'))
      })
    )

    render(<App />)

    await waitFor(() => expect(screen.getByText(/API OFFLINE/)).toBeInTheDocument())
  })

  it('submits an analysis and displays the eligibility result', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/opportunities/analyse')) {
        return Promise.resolve(
          responseFor({
            title: 'PhD in AI',
            institution: 'Example University',
            degree_type: 'PhD',
            eligibility: 'Action required',
            matched_requirements: ["Bachelor's degree"],
            missing_requirements: ['English proficiency'],
            evidence_summary: ["Bachelor's degree completed"],
            requirement_results: [],
            deadline: '15 September 2026',
            deadline_date: '2026-09-15',
            funding: 'No funding available',
            funding_status: 'unavailable',
            required_documents: [],
          })
        )
      }
      if (url.endsWith('/api/v1/tasks/generate')) {
        return Promise.resolve(responseFor([]))
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText(/API CONNECTED/)).toBeInTheDocument())

    fireEvent.change(screen.getByRole('textbox', { name: 'Requirements (one per line)' }), {
      target: { value: "Bachelor's degree\nEnglish proficiency" },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Evidence (one per line)' }), {
      target: { value: "Bachelor's degree completed" },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Analyse opportunity' }))

    await waitFor(() => expect(screen.getByText('Review ready for PhD in AI.')).toBeInTheDocument())
    expect(screen.getAllByText('Action required').length).toBeGreaterThan(0)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/opportunities/analyse'),
      expect.objectContaining({ method: 'POST' })
    )
  })
})
