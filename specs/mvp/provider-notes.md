# Supplied Provider Documentation and Design Workflow

Evidence date: 2026-10-10. These notes summarize official documentation supplied
by the user as pasted files/text. Live website retrieval previously returned 403.
Documented support is distinct from successful access using an actual account.
No credentials, quota checks, installation, or model calls occurred in planning.

## Source Register

| Source title | Canonical reference | Evidence used |
|---|---|---|
| Tool Use Overview - GroqDocs | https://console.groq.com/docs/tool-use | Capability table; local/remote/built-in distinction; tool IDs/results |
| Supported Models - GroqDocs | https://console.groq.com/docs/models | Production/preview classifications; context/output; Developer-plan price/limits |
| Local Tool Calling - GroqDocs | https://console.groq.com/docs/tool-use/local-tool-calling | Schema/function/orchestration separation; tool choice; validation/errors |
| Reasoning - GroqDocs | https://console.groq.com/docs/reasoning | GPT-OSS-specific reasoning parameters; JSON/tool compatibility |
| Rate Limits - GroqDocs | https://console.groq.com/docs/rate-limits | Organization-level quotas; numeric table; response headers; 429 behavior |
| Impeccable Install & first steps | https://impeccable.style/tutorials/getting-started/ | Node prerequisite; installation, context, design, review, audit |

The supplied texts have no reliable original publication/version timestamps.
Use the evidence date above, preserve the source links, and recheck changes at
implementation time. Avoid copying unrelated code examples or their emojis.

## Groq Candidate

Propose `openai/gpt-oss-20b` for the first controlled evaluation. The supplied
model table lists it as production, with a 131,072-token context window and
65,536 maximum completion tokens. The tool table documents local/remote tool
use and JSON mode, and explicitly says no parallel tool-use support.

The supplied production table lists Developer-plan pricing of USD 0.075 input
and USD 0.30 output per million tokens, with 250K TPM and 1K RPM. Those values
are not free-plan quotas or proof of free account availability. Never place them
in the application as free-tier limits. The separately supplied quota table is
recorded below. P-01 remains open for actual account eligibility/limits, retention,
Spanish quality, and live schema behavior.

T17 pins the Spanish spaCy model package `es_core_news_sm` 3.8.0 from the
official spaCy model release wheel in `uv.lock`. It runs locally before the
confirmation endpoint can make a provider request; failure to load the model
fails closed. NER quality is not a guarantee that every human name is detected,
so structured sender/recipient/contact variants, conservative proper-noun
redaction, and output validation remain in place. Actual Groq account/model
eligibility and free-plan limits remain unverified until P-01.

`openai/gpt-oss-120b` is also documented as production with local tools/JSON and
no parallel tools. It is an optional explicitly configured candidate, never an
automatic cost/size fallback. Preview Qwen/MiniMax models are not default choices.
Do not infer free eligibility from any production/preview label.

## Supplied Quotas and Plan-Label Ambiguity

The user identifies the latest rate-limit extract as including Free. Its table
lists the following values, but its preceding paragraph calls the displayed
limits Developer base limits. The pasted extract does not preserve a Free tab
label. Record these as documented table values with a PROVISIONAL Free-plan
attribution, not independently verified Free entitlements:

| Model | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `openai/gpt-oss-20b` | 30 | 1,000 | 8,000 | 200,000 |
| `openai/gpt-oss-120b` | 30 | 1,000 | 8,000 | 200,000 |
| `openai/gpt-oss-safeguard-20b` | 3 | 1,000 | 2,000 | 200,000 |
| `qwen/qwen3.8-27b` | 30 | 1,000 | 8,000 | 200,000 |

Use `https://console.groq.com/settings/limits` with the actual organization and
plan during T00 to resolve the attribution. Organization-specific limits take
precedence over either public table. The conflict does not justify using the
much larger Supported Models Developer quotas as Free defaults.

Limits are organization-wide, not per application user or API key. Enforce all
applicable RPM/RPD/TPM/TPD and optional ITPM/OTPM dimensions. Multiple analyses,
follow-ups, retries, and usage outside this app share the upstream allowance.
Cached tokens do not count toward documented quotas; reserve uncached estimates
conservatively until actual cache/usage evidence is available. Do not assume a
cache hit or invent a guaranteed analyses-per-day figure.

The documented header mappings are important:

| Headers | Dimension |
|---|---|
| `x-ratelimit-limit-requests`, `remaining-requests`, `reset-requests` with the same prefix | Requests per day, not requests per minute |
| `x-ratelimit-limit-tokens`, `remaining-tokens`, `reset-tokens` with the same prefix | Tokens per minute, not tokens per day |
| `retry-after` | Seconds until retry; present on a rate-limited 429 response |

Parse documented reset durations, not a guessed Unix timestamp. These headers
do not report every quota dimension; RPM/TPD and split input/output limits still
need configured caps and conservative local accounting. Missing/stale headers
never authorize bypassing configured quotas. Persist shared reservations using
MongoDB so simultaneous users or a worker restart cannot reset the allowance.
Reconcile headers/usage conservatively, and return a recoverable quota state if
the next safe call will exceed the analysis deadline. Do not retry 400 contract
errors as quota failures, and never upgrade billing automatically.

## Local Tool-Calling Contract

LangGraph orchestrates functions inside the application. Groq receives only
allowlisted function definitions and redacted messages/results. Do not enable
Groq-hosted browser search/code execution or remote MCP for this MVP.

1. Construct JSON Schema tool definitions from typed Pydantic contracts.
2. Send a bounded initial request with the allowed tools and trusted internal
   instructions. Use `tool_choice="auto"` normally; a verification fixture can
   force a named harmless local tool.
3. Parse `function.arguments` as untrusted JSON and validate it. Match names
   against the allowlist; never dynamically import/evaluate requested names.
4. Execute allowed calls serially with a bounded tool-call budget. Do not set
   `parallel_tool_calls=true` for GPT-OSS. Any unexpected multiple requests are
   validated and processed serially only within the remaining budget.
5. Append the assistant tool-call message and one `role="tool"` response per
   accepted call, preserving the exact `tool_call_id` association. Return only
   role keys, counts, taxonomy, and other approved non-identifying data.
6. Send the bounded follow-up, with `tool_choice="none"` when producing final
   suggestions. If the graph cannot finish within two provider passes, stop
   safely instead of silently extending the agent loop.
7. Validate every suggestion using Pydantic and source hashes before exposing it.

JSON mode means valid JSON output, not guaranteed conformity to the full business
schema. The supplied docs include schema-oriented examples but do not prove all
`strict`/`json_schema`/tool combinations for every model. Test the selected SDK
and model combination in T00/T17. Never rely solely on provider validation.

## Reasoning Parameters and Conflicts

Use the specific GPT-OSS section over the generic reasoning table: do not send
`reasoning_format` for GPT-OSS. Proposed settings are `include_reasoning=false`
and `reasoning_effort="low"`. Never combine `include_reasoning` with
`reasoning_format`. Hiding returned reasoning does not guarantee elimination of
reasoning token usage; measure `usage` and reserve completion budget accordingly.
Do not persist/display hidden reasoning. Produce concise explicit suggestion
reasons through the application schema instead.

Other supplied sections contain conflicting examples: a parallel-tool example
names GPT-OSS despite the capability table saying no, and generic prompt advice
mentions DeepSeek or avoiding system prompts while the local-tool guide uses
system prompts. Preserve trusted application-owned instructions and document
text as separate inputs. Verify the chosen model's role handling rather than
moving policy into untrusted letter text. Parameter 400 errors are contract
failures to diagnose, not instructions to relax access/privacy restrictions.

## Impeccable Implementation Workflow

The supplied tutorial requires Node.js 22.18 or later; repository Node 24 meets
that baseline. During T11, `impeccable@4.5.2` was queried and the official
installer was attempted with `pnpm dlx`; its style-site bundle returned HTTP
403. The public GitHub source was then added as `vendor/impeccable`, pinned at
commit `d631a8827f99414d2b6daba4ef08b7f8701751d7` (package version 4.5.2), and
linked for Codex with the pinned CLI's `link --source=vendor/impeccable
--providers=codex` command. The resulting project skill was read and its version
verified. The optional design hook was declined.

The mechanical detector was invoked once for T11 but its Chromium launch failed
because of the environment's Crashpad/SUID sandbox configuration. No retry was
made under the skill's one-run rule; an independent system-Chromium/Playwright
visual and functional check was performed instead. The user accepted merging
T11 with this validation limitation recorded. The broader visual direction is
not finalized; the user intends to refine it manually.

From the project root, use only pnpm. Future commands:

```sh
pnpm dlx "impeccable@<PINNED_VERSION>" install
```

Select Codex and project scope in the installer, then reload the coding tool.
Verify skill discovery before claiming it is installed. If this installer fails,
diagnose or use an approved local-source workflow; never switch to npm/npx.

In the coding-agent chat, run `/impeccable init` and review the generated
`PRODUCT.md`. Context must state academic members, Markdown/PDF split editing,
collaboration, quick recipient correction, privacy-conscious signing, minimal
clicks, Spanish UI, mobile use, keyboard access, and Bootstrap Icons only.
Keep product and design documentation in English under `/AGENTS.md`.

Prefer the code-led workflow for this MVP's constrained editor. If retaining an
existing UI style, `/impeccable document` records agreed reusable rules in
`DESIGN.md`. The supplied academic PDF header/footer is a document design to
preserve, not a reason to copy PDF typography into every application control.

For new work use `/impeccable design` after selecting one task's interface scope.
For inspection use `/impeccable critique`; use `/impeccable polish` to refine an
existing page. Use `/impeccable audit` before UI acceptance. A specification-only
stage can use `/impeccable shape` after installation; it must not trigger builds
under the current planning-only instruction.

For later updates, review the chosen submodule revision, then use
`pnpm dlx "impeccable@<PINNED_VERSION>" link --source=vendor/impeccable
--providers=codex`. Do not copy a Claude/Cursor provider list for Codex.
Preserve existing skill directories; do not use `--force` to overwrite them.
Installing skills does not automatically install or authorize design hooks.

Review actual task behavior on desktop and narrow screens, inspect code, and
verify accessibility/performance. Preserve agreed product/design context across
tasks. Impeccable guidance never overrides signature privacy or product rules.
