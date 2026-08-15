# ApplyLens AI free public beta terms

Effective 15 August 2026. These terms describe the ApplyLens AI free public
beta, release `0.1.0-beta.1`. They are written as a plain-language product
contract and should be reviewed for the operator's jurisdiction before a public
launch.

## Service boundary

ApplyLens provides informational decision support for Master's and PhD
applications. It organizes candidate evidence, extracts academic-call details,
reports eligibility as supported, unsupported, unclear, or actionable, and
tracks application work.

ApplyLens does not submit applications, represent a university, provide legal
or admissions advice, or guarantee eligibility, admission, funding, deadlines,
or any other outcome. The candidate must verify important information against
the original academic call and remains responsible for every decision and
submission.

## Account data and retention

ApplyLens stores account details, a structured candidate profile, uploaded PDF
and TXT files and their extracted text, opportunity text, evidence chunks,
reviews, tasks, sessions, security records, and the account's external-AI
consent choice. Account-owned application data is isolated from other users.

A signed-in user can export their account data, delete individual supported
records, or permanently delete the account. Account deletion removes active
application data and uploaded files. Deleted data may remain in access-restricted
operational backups until those backups reach their scheduled rotation; backups
are used only for disaster recovery.

## External AI and automated analysis

External AI processing is off by default. It is used only when the operator has
configured an external embedding provider and the account holder explicitly
opts in. In that mode, opportunity text and evidence-search queries may be sent
to the configured provider. Consent can be withdrawn for future processing;
information already sent remains subject to that provider's processing terms.

PDF extraction, opportunity parsing, retrieval, and eligibility analysis can be
incomplete or wrong. Missing evidence is not proof that a requirement is absent,
and a match is not an official eligibility decision. Users must inspect cited
evidence and the original source.

## Acceptable use

Users may upload only content they own or are authorized to process. The service
must not be used for unlawful, abusive, fraudulent, or harmful content; malware;
impersonation; unauthorized access or security probing; bypassing quotas or rate
limits; or disrupting ApplyLens or other users.

## Beta operation and support

The beta is provided without a paid-service availability commitment. Features,
limits, and data formats may change, and users should keep their own copies of
important application material. The public operator must configure and monitor
`SUPPORT_EMAIL`; security and operational incidents must route to the private
`INCIDENT_CONTACT_EMAIL`. Neither address nor any credential should be hard-coded
in the repository.
