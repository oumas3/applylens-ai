export type ProductInfo = {
  name: string
  version: string
  release_channel: 'free-public-beta'
  phase: string
  supported_opportunities: string[]
  promise: string
  support_email: string | null
}

type LegalInfoPanelProps = {
  product: ProductInfo
  onClose: () => void
}

export default function LegalInfoPanel({ product, onClose }: LegalInfoPanelProps) {
  return (
    <section className="legal-panel" aria-labelledby="legal-heading">
      <div className="legal-header">
        <div>
          <p className="eyebrow">PUBLIC BETA INFORMATION</p>
          <h2 id="legal-heading">Privacy, terms &amp; support</h2>
          <p className="analysis-status">
            Please read this summary before creating an account or relying on an
            opportunity review. Effective 15 August 2026.
          </p>
        </div>
        <button className="ghost" type="button" onClick={onClose}>
          Close information
        </button>
      </div>

      <div className="legal-grid">
        <article id="privacy-information">
          <h3>Privacy and your data</h3>
          <p>
            ApplyLens stores your account, candidate profile, uploaded document files
            and extracted text, opportunity text, reviews, and tasks. This information
            is private to your account and is retained until you delete individual
            records or permanently delete your account.
          </p>
          <p>
            You can download an account export and delete your account from the signed-in
            Privacy &amp; data panel. Deleted data may remain in restricted operational
            backups until their scheduled rotation, and backups are used only for
            disaster recovery.
          </p>
        </article>

        <article id="ai-information">
          <h3>External AI and limitations</h3>
          <p>
            External AI is off by default. If an operator configures an external
            embedding provider and you explicitly opt in, opportunity text and evidence
            search queries may be sent to that provider. You can turn consent off for
            future processing; data already sent remains subject to the provider's
            processing terms.
          </p>
          <p>
            Automated extraction and analysis can be incomplete or wrong. ApplyLens
            marks missing evidence as unclear or actionable, but you must verify every
            important requirement against the original academic call.
          </p>
        </article>

        <article id="terms-information">
          <h3>Terms of use</h3>
          <p>
            ApplyLens provides informational decision support for Master's and PhD
            applications. It does not submit applications, represent a university,
            provide legal or admissions advice, or guarantee eligibility, admission,
            funding, deadlines, or outcomes. You remain responsible for your decisions
            and submissions.
          </p>
        </article>

        <article id="acceptable-use-information">
          <h3>Acceptable use</h3>
          <p>
            Upload only documents you own or are authorized to process. Do not use the
            service for unlawful, abusive, or harmful content; malware; unauthorized
            access or security probing; rate-limit bypass; impersonation; or disruption
            of ApplyLens or other users.
          </p>
        </article>

        <article id="support-information">
          <h3>Support and release</h3>
          <p>
            {product.name} {product.version} is a {product.release_channel.replace(/-/g, ' ')}
            {' '}release. Features and limits may change during the beta; keep your own
            copies of important application material.
          </p>
          <p>
            {product.support_email ? (
              <>
                Need help or want to report a privacy or security issue? Email{' '}
                <a href={`mailto:${product.support_email}`}>{product.support_email}</a>.
              </>
            ) : (
              <>
                Support contact is not configured in this development environment. The
                public deployment must publish an operator-monitored support address.
              </>
            )}
          </p>
        </article>
      </div>
    </section>
  )
}
