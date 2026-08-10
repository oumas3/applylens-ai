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
  if (url.endsWith('/api/v1/auth/me')) {
    return responseFor({ id: 'test-user', email: 'test@example.com', is_active: true })
  }
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
  window.history.replaceState({}, '', '/')
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

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /Know where you qualify/i })).toBeInTheDocument()
    )
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

  it('changes the password from the account security panel', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/password')) {
        return Promise.resolve(responseFor({}, 204))
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText(/API CONNECTED/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Security' }))
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'correct horse battery' },
    })
    fireEvent.change(screen.getByLabelText('New password (at least 12 characters)'), {
      target: { value: 'a different secure password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Update password' }))

    await waitFor(() =>
      expect(
        screen.getByText('Password updated. Other signed-in devices were disconnected.')
      ).toBeInTheDocument()
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/password'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          current_password: 'correct horse battery',
          new_password: 'a different secure password',
        }),
      })
    )
  })

  it('requests a password reset without exposing account status', async () => {
    const safeMessage =
      'If an active account matches that email, a password reset link will be sent.'
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/me')) {
        return Promise.resolve(responseFor({ detail: 'Authentication required.' }, 401))
      }
      if (url.endsWith('/api/v1/auth/password-reset/request')) {
        return Promise.resolve(responseFor({ message: safeMessage }, 202))
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText('Welcome back.')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Forgot password?' }))
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'candidate@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => expect(screen.getByText(safeMessage)).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/password-reset/request'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'candidate@example.com' }),
      })
    )
  })

  it('confirms a reset token from the URL and returns to sign in', async () => {
    window.history.replaceState({}, '', '/#reset_token=one-time-token-value-123456789')
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/me')) {
        return Promise.resolve(responseFor({ detail: 'Authentication required.' }, 401))
      }
      if (url.endsWith('/api/v1/auth/password-reset/confirm')) {
        return Promise.resolve(responseFor({}, 204))
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() =>
      expect(screen.getByText('Choose a new password.')).toBeInTheDocument()
    )

    fireEvent.change(screen.getByLabelText('New password (at least 12 characters)'), {
      target: { value: 'a different secure password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() =>
      expect(screen.getByText('Password reset. Sign in with your new password.')).toBeInTheDocument()
    )
    expect(screen.getByText('Welcome back.')).toBeInTheDocument()
    expect(window.location.hash).toBe('')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/password-reset/confirm'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          token: 'one-time-token-value-123456789',
          new_password: 'a different secure password',
        }),
      })
    )
  })
})
