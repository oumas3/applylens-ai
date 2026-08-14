type OnboardingPanelProps = {
  documentCount: number
  profileItemCount: number | null
  opportunityCount: number
  reviewCount: number
  taskCount: number
  loading: boolean
}

type OnboardingStep = {
  id: string
  title: string
  description: string
  targetId: string
  action: string
  complete: boolean
}

function goTo(targetId: string) {
  document.getElementById(targetId)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

export default function OnboardingPanel({
  documentCount,
  profileItemCount,
  opportunityCount,
  reviewCount,
  taskCount,
  loading,
}: OnboardingPanelProps) {
  const steps: OnboardingStep[] = [
    {
      id: 'document',
      title: 'Upload candidate evidence',
      description: 'Add a CV, transcript, letter, or other supporting PDF or TXT file.',
      targetId: 'document-upload',
      action: 'Upload evidence',
      complete: documentCount > 0,
    },
    {
      id: 'profile',
      title: 'Build your candidate profile',
      description: 'Save reusable education, research, language, and skill claims.',
      targetId: 'candidate-profile',
      action: 'Build profile',
      complete: (profileItemCount ?? 0) > 0,
    },
    {
      id: 'opportunity',
      title: 'Extract an academic call',
      description: 'Upload a Master’s or PhD call so its requirements remain traceable.',
      targetId: 'opportunity-analysis',
      action: 'Add opportunity',
      complete: opportunityCount > 0,
    },
    {
      id: 'review',
      title: 'Review eligibility evidence',
      description: 'Analyse a call and save the evidence-backed result in your workspace.',
      targetId: 'opportunity-analysis-form',
      action: 'Run analysis',
      complete: reviewCount > 0,
    },
    {
      id: 'tasks',
      title: 'Track the application work',
      description: 'Turn missing requirements, documents, and deadlines into clear tasks.',
      targetId: 'task-tracker',
      action: 'View tasks',
      complete: taskCount > 0,
    },
  ]
  const completedCount = steps.filter((step) => step.complete).length
  const progressLabel = `${completedCount} of ${steps.length} setup steps complete`

  return (
    <section className="onboarding-panel" aria-labelledby="onboarding-heading">
      <div className="onboarding-header">
        <div>
          <p className="eyebrow">GET STARTED</p>
          <h2 id="onboarding-heading">Your application workspace, step by step</h2>
          <p className="analysis-status">
            Follow this evidence-first workflow once, then reuse your saved profile for every call.
          </p>
        </div>
        <div className="onboarding-progress">
          <strong>{loading ? 'Loading…' : `${completedCount}/${steps.length}`}</strong>
          <progress value={completedCount} max={steps.length} aria-label={progressLabel} />
          <span>{progressLabel}</span>
        </div>
      </div>

      <ol className="onboarding-steps">
        {steps.map((step, index) => (
          <li className={step.complete ? 'complete' : ''} key={step.id}>
            <span className="onboarding-step-number" aria-hidden="true">
              {step.complete ? '✓' : index + 1}
            </span>
            <div>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </div>
            {step.complete ? (
              <span className="onboarding-complete">Complete</span>
            ) : (
              <button className="ghost" type="button" onClick={() => goTo(step.targetId)}>
                {step.action}
              </button>
            )}
          </li>
        ))}
      </ol>

      <p className="sr-status" aria-live="polite">
        {loading
          ? 'Loading your onboarding progress.'
          : completedCount === steps.length
            ? 'Workspace setup complete. You are ready to manage applications.'
            : progressLabel}
      </p>
    </section>
  )
}
