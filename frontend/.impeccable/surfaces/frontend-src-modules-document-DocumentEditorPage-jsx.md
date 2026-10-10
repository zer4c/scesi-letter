---
version: 1
slug: "frontend-src-modules-document-DocumentEditorPage-jsx"
primary_target: "frontend/src/modules/document/DocumentEditorPage.jsx"
related_targets:
  - "frontend/src/modules/document/DocumentListPage.jsx"
  - "frontend/src/styles.css"
---

Scope: collaborative academic letter editing and PDF preview. Mode: Operate.

Audience and task: SCESI members create and revise academic correspondence with
structured metadata and Markdown, collaborate through the authenticated Yjs
room, inspect an unsigned PDF preview, and explicitly save to allocate a letter
identifier and immutable version. Preserve the existing SCESI Letter interface
tokens and Spanish UI. The broader design system remains open for later manual
refinement.

## Direction contract

THESIS: Keep the authoring surface focused on the relationship between letter
fields, optional academic event/topic classification, editable Markdown, shared
changes, and the resulting PDF. Do not turn it into an analytics dashboard or
add unspecced workflows.

OWN-WORLD: Extend the existing white/warm-gray SCESI Letter workspace with
institutional red for primary actions and active states, Onest typography,
charcoal-violet text, fine separators, visible focus, and restrained geometry.
The academic PDF template is rendered content, not application chrome.

STORY: The member edits synchronized fields and body, sees connection and save
state, checks the newest available PDF preview, and explicitly saves. The first
explicit save allocates the identifier; autosync does not number a draft.

FIRST VIEWPORT: Desktop presents metadata and Markdown beside an unsigned PDF
preview. At widths through 900px, Edit and Preview tabs keep the PDF readable
without squeezing it into a narrow column. Loading, disconnected, validation,
preview failure, save conflict, and empty-list states remain recoverable.

FORM: Use the product's single default template. Do not add template selection,
document deletion, automatic AI actions, signatures, or delivery controls here.

FINISH: verify desktop and mobile composition, keyboard labels/focus, current
preview response ordering, save conflict handling, and the production bundle.
