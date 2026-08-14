import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
    return responseFor({
      id: 'test-user',
      email: 'test@example.com',
      is_active: true,
      external_ai_consent: false,
    })
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
  if (url.endsWith('/api/v1/profile')) {
    return responseFor({
      user_id: 'test-user',
      updated_at: null,
      full_name: null,
      headline: null,
      location: null,
      summary: null,
      education: [],
      work_experience: [],
      research_experience: [],
      languages: [],
      skills: [],
      publications: [],
    })
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

  it('loads and updates external AI consent from the privacy panel', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/account/privacy')) {
        return Promise.resolve(
          responseFor({
            external_ai_consent: init?.method === 'PUT',
            external_ai_configured: true,
            external_ai_provider: 'OpenAI',
          })
        )
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText(/API CONNECTED/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Privacy & data' }))

    const consent = await screen.findByRole('checkbox', {
      name: 'Allow external AI processing for semantic evidence search',
    })
    expect(consent).not.toBeChecked()
    fireEvent.click(consent)

    await waitFor(() => expect(screen.getByText('External AI processing enabled.')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/account/privacy'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ external_ai_consent: true }),
      })
    )
  })

  it('builds and saves an evidence-linked candidate profile', async () => {
    const document = {
      id: 'document-1',
      original_filename: 'candidate-cv.txt',
      stored_filename: 'document-1.txt',
      category: 'CV',
      content_type: 'text/plain',
      size_bytes: 100,
      status: 'uploaded',
      extracted_text_length: 100,
      uploaded_at: '2026-08-14T10:00:00Z',
    }
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/documents')) {
        return Promise.resolve(responseFor([document]))
      }
      if (url.endsWith('/api/v1/profile') && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body))
        return Promise.resolve(
          responseFor({
            ...body,
            user_id: 'test-user',
            updated_at: '2026-08-14T10:05:00Z',
          })
        )
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    const profileHeading = await screen.findByRole('heading', {
      name: 'Build reusable, evidence-linked credentials',
    })
    const profileSection = profileHeading.closest('section')
    expect(profileSection).not.toBeNull()
    const profileForm = within(profileSection as HTMLElement)
    fireEvent.change(profileForm.getByLabelText('Full name'), {
      target: { value: 'Candidate Example' },
    })
    fireEvent.click(profileForm.getByRole('button', { name: 'Add education' }))
    fireEvent.change(profileForm.getByLabelText('Degree'), {
      target: { value: "Master's degree" },
    })
    fireEvent.change(profileForm.getByLabelText('Field of study'), {
      target: { value: 'Artificial Intelligence' },
    })
    fireEvent.change(profileForm.getByLabelText('Institution'), {
      target: { value: 'Example University' },
    })
    const evidenceDocuments = profileForm.getByLabelText(
      /^Evidence documents/
    ) as HTMLSelectElement
    const cvOption = profileForm.getByRole('option', { name: 'candidate-cv.txt' }) as HTMLOptionElement
    cvOption.selected = true
    fireEvent.change(evidenceDocuments)
    fireEvent.click(profileForm.getByRole('button', { name: 'Save candidate profile' }))

    await waitFor(() =>
      expect(
        screen.getByText('Profile saved. Evidence-linked claims are ready for analysis.')
      ).toBeInTheDocument()
    )
    const profileCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith('/api/v1/profile') && init?.method === 'PUT'
    )
    expect(profileCall).toBeDefined()
    const savedProfile = JSON.parse(String(profileCall?.[1]?.body))
    expect(savedProfile.full_name).toBe('Candidate Example')
    expect(savedProfile.education).toEqual([
      expect.objectContaining({
        degree: "Master's degree",
        field_of_study: 'Artificial Intelligence',
        institution: 'Example University',
        document_ids: ['document-1'],
      }),
    ])
  })

  it('permanently deletes the account after explicit confirmation', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/account/privacy')) {
        return Promise.resolve(
          responseFor({
            external_ai_consent: false,
            external_ai_configured: false,
            external_ai_provider: null,
          })
        )
      }
      if (url.endsWith('/api/v1/account') && init?.method === 'DELETE') {
        return Promise.resolve(responseFor({}, 204))
      }
      return Promise.resolve(defaultFetchResponse(url, init?.method ?? 'GET'))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(screen.getByText(/API CONNECTED/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Privacy & data' }))
    fireEvent.change(await screen.findByLabelText('Current password'), {
      target: { value: 'correct horse battery' },
    })
    fireEvent.change(screen.getByLabelText('Type DELETE to confirm'), {
      target: { value: 'DELETE' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Delete my account permanently' }))

    await waitFor(() => expect(screen.getByText('Welcome back.')).toBeInTheDocument())
    expect(
      screen.getByText('Your account and stored data were permanently deleted.')
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/account'),
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({
          current_password: 'correct horse battery',
          confirmation: 'DELETE',
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
