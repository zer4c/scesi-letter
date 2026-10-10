---
version: 1
slug: "frontend-src-app-jsx"
primary_target: "frontend/src/App.jsx"
related_targets: []
---

Scope: authentication, invitation acceptance, and the authenticated application shell. Mode: Operate.

Audience and task: invited SCESI members sign in or establish an account from an invitation, then reach their authorized letter workspace. They need clear session, loading, validation, and expiry states. Keep the editor and academic PDF template unchanged; do not invent documents or unfinished actions.

## Direction contract

THESIS: Make access to SCESI Letter feel unmistakably connected to its university community while keeping authentication as a direct, familiar web task. Refuse the generic dashboard/login combination with an oversized analytics panel or decorative card grid.

OWN-WORLD: UMSS institutional geometry, selected as candidate 5 of seven grounded directions (seed 134f0806; degraded roll, no challenger catalog). Use the approved deep institutional red (#a40000), white, charcoal violet (#25243a), and pale warm gray (#f2f0ed) as purposeful surface, type, state, and identity roles. Workhorse sans-serif carries forms and navigation. Crisp geometry derived from the supplied university pennant is a single restrained identity cue; standard web controls remain standard. Never recreate the PDF header in application chrome.

STORY: A member immediately recognizes SCESI Letter, completes sign-in or invitation setup, and understands a rejected/expired session and its recovery path. After authentication, persistent navigation identifies the letter workspace, the member, and logout; administrators alone see organization access.

FIRST VIEWPORT: On desktop, use a two-region frame: a broad identity field carries the SCESI Letter name, a concise academic-workspace description, and a small geometric pennant cue; a narrower, quiet access region holds one focused, labeled form and its primary action. Place invitation/recovery guidance beside the form, not in a second card. On mobile, stack identity then form, with the form immediately usable and no horizontal scrolling. The signed-in shell uses ordinary responsive navigation, with page content as the dominant region and no fabricated analytics.

FORM: Operate surface, code-led per the session default. Candidate 5, assigned by seed 134f0806; approved by the user as “Geometría institucional.” The structured fallback did not offer a build-path toggle. The sign-in and invitation forms are the surface expression; editor composition and PDF remain later tasks.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
