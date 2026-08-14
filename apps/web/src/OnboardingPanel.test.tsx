import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OnboardingPanel from './OnboardingPanel'

afterEach(() => {
  cleanup()
})

describe('OnboardingPanel', () => {
  it('shows real workspace progress and navigates to an incomplete step', () => {
    const target = document.createElement('div')
    target.id = 'candidate-profile'
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)

    render(
      <OnboardingPanel
        documentCount={1}
        profileItemCount={0}
        opportunityCount={0}
        reviewCount={0}
        taskCount={0}
        loading={false}
      />
    )

    expect(screen.getByRole('progressbar')).toHaveValue(1)
    expect(screen.getAllByText('1 of 5 setup steps complete')).toHaveLength(2)
    expect(screen.getByText('Upload candidate evidence').closest('li')).toHaveClass('complete')

    fireEvent.click(screen.getByRole('button', { name: 'Build profile' }))
    expect(target.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    })

    target.remove()
  })

  it('recognizes a fully prepared workspace', () => {
    render(
      <OnboardingPanel
        documentCount={2}
        profileItemCount={3}
        opportunityCount={1}
        reviewCount={1}
        taskCount={4}
        loading={false}
      />
    )

    expect(screen.getByRole('progressbar')).toHaveValue(5)
    expect(screen.getAllByText('Complete')).toHaveLength(5)
    expect(
      screen.getByText('Workspace setup complete. You are ready to manage applications.')
    ).toBeInTheDocument()
  })
})
