---
name: SCESI Letter
description: Institutional tools for authoring and managing academic correspondence.
colors:
  institutional: "#a40000"
  institutional-dark: "#7f0000"
  ink: "#25243a"
  muted: "#5d5b66"
  paper: "#ffffff"
  ground: "#f2f0ed"
  line: "#dedbd7"
  error: "#8e1f1f"
  error-ground: "#fceeed"
  info: "#244c62"
  info-ground: "#edf4f7"
typography:
  body:
    fontFamily: "Onest Variable, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  headline:
    fontFamily: "Onest Variable, Segoe UI, sans-serif"
    fontSize: "clamp(3rem, 6.5vw, 6rem)"
    fontWeight: 650
    lineHeight: 0.99
    letterSpacing: "-0.04em"
  title:
    fontFamily: "Onest Variable, Segoe UI, sans-serif"
    fontSize: "clamp(2rem, 3vw, 2.65rem)"
    fontWeight: 650
    lineHeight: 1.1
    letterSpacing: "-0.035em"
  label:
    fontFamily: "Onest Variable, Segoe UI, sans-serif"
    fontSize: "0.93rem"
    fontWeight: 600
    lineHeight: 1.55
  button:
    fontFamily: "Onest Variable, Segoe UI, sans-serif"
    fontSize: "0.93rem"
    fontWeight: 650
    lineHeight: 1.55
rounded:
  control: "7px"
  surface: "12px"
spacing:
  xs: "2px"
  sm: "8px"
  md: "12px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.institutional}"
    textColor: "{colors.paper}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "12px 18px"
    height: "50px"
  input-text:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 13px"
    height: "50px"
  input-compact:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 11px"
    height: "42px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.institutional-dark}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "42px"
  button-workspace:
    backgroundColor: "{colors.institutional}"
    textColor: "{colors.paper}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "9px 17px"
    height: "44px"
  editor-panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.surface}"
---

# Design System: SCESI Letter

## Overview

**Creative North Star: “Geometría institucional”**

The shipped access and navigation slice uses a clear institutional frame: a broad red identity field beside a quiet white form, followed after sign-in by a light workspace shell. Onest carries both prominent Spanish headings and everyday controls. The supplied SCESI and university marks remain the authority for institutional identity; the application adds only a small crossing-line pennant cue.

This record describes the established T11 access and navigation system and its shipped T12 document-editor extension. The editor reuses the workspace palette, Onest typography, focus treatment, and restrained institutional geometry while adding compact field sizing, paired authoring and preview panels, and a narrow-screen edit/preview switch. These surface-specific choices document the current implementation; broader visual refinement remains open for later manual work.

**Key Characteristics:**
- Institutional red anchors identity, actions, and active navigation.
- Warm gray grounds the workspace; white carries focused content.
- Crisp geometry and restrained borders keep the interface direct.

## Colors

The palette pairs institutional red and charcoal-violet text with white, warm gray, and restrained semantic status colors.

### Primary
- **Institutional red** (`{colors.institutional}`): Brand field, primary actions, active navigation marker, and selected interface accents.
- **Deep institutional red** (`{colors.institutional-dark}`): Hover treatment for primary actions and links.

### Neutral
- **Charcoal violet** (`{colors.ink}`): Main text and headings.
- **Muted charcoal** (`{colors.muted}`): Supporting copy, metadata, and secondary navigation.
- **White** (`{colors.paper}`): Access form and application header surfaces.
- **Warm gray** (`{colors.ground}`): Workspace page background.
- **Soft gray line** (`{colors.line}`): Header, footer, and document separators.

### Named Rules
**The Identity Accent Rule.** Reserve institutional red for identity, primary actions, and clear active or hover states; keep ordinary workspace surfaces neutral.

**The Status Color Rule.** Use the distinct error and information pairs for notices, not as general decoration.

## Typography

**Display Font:** Onest Variable (with Segoe UI, sans-serif fallback)
**Body Font:** Onest Variable (with Segoe UI, sans-serif fallback)
**Label/Mono Font:** No separate label or monospace family is used.

**Character:** A single workhorse sans-serif keeps forms and navigation familiar. Tight tracking and compact leading distinguish large headings without introducing a second display face.

### Hierarchy
- **Display** (650, `clamp(3rem, 6.5vw, 6rem)`, 0.99 line-height): Identity statement in the access panel.
- **Headline** (650, `clamp(2.4rem, 5vw, 3.4rem)`, 1.04 line-height): Main authenticated page heading.
- **Title** (650, `clamp(2rem, 3vw, 2.65rem)`, 1.1 line-height): Access form heading; smaller section titles use 1.15rem at the same family.
- **Body** (400, 16px, 1.55 line-height): Default reading and control text.
- **Label** (600, 0.93rem): Form labels; navigation and actions use semibold weights around 0.9–0.94rem.

### Named Rules
**The One-Family Rule.** Use Onest Variable throughout this surface; rely on size, weight, and spacing for hierarchy.

## Layout

Desktop access uses a two-column frame, with the identity region wider than the form region. The form stays within a 420px inner width. At 900px, the split narrows and authenticated navigation moves to a second header row; at 680px, access stacks identity above the form and the authenticated header retains navigation below its brand/account row. The workspace content is centered at up to 1120px with 20–24px minimum side gutters. The document editor uses paired authoring and PDF-preview columns on wider screens. At 900px and below it changes to one column with Edit and Preview tabs, keeping the PDF readable instead of compressing it beside the fields. At narrow widths, document rows stack their metadata under the main text, and editor field pairs stack below 420px.

Spacing is a compact 2, 8, 12, 20, and 24px rhythm, with larger section gaps and responsive outer padding where needed. Reduced-motion preferences shorten transitions and animations.

## Elevation & Depth

Workspace panels are flat at rest. White and warm gray establish the main surface separation, with thin rules for structure; rendered PDF pages receive a subtle sheet shadow. Focus uses a translucent red ring around fields, paired with a strong visible outline for keyboard focus.

### Shadow Vocabulary
- **Field focus ring** (`0 0 0 3px rgb(164 0 0 / 18%)`): Draws attention to the active text field.
- **PDF page** (`0 2px 8px rgb(37 36 58 / 16%)`): Separates rendered pages from the gray preview well.

### Named Rules
**The Flat Surface Rule.** Use surface color and fine separators for structure; reserve the soft ring for an actively focused field.

## Shapes

Controls use gently rounded corners (7px); editor panels have a softer 12px corner. The overall form language is rectangular and crisp, with thin borders on fields and no decorative card grid.

## Components

### Buttons
- **Character:** Compact, direct actions with clear primary and quiet treatments.
- **Shape:** Control radius (7px).
- **Primary:** Institutional red fill, white semibold text, 50px minimum height, and 12px by 18px padding. Hover darkens and lifts by 1px; active returns to rest; disabled communicates waiting with reduced opacity.
- **Quiet:** Transparent background, dark red text, 42px minimum height; hover adds a pale red surface and border.
- **Focus:** Keyboard focus receives a visible 3px outline with offset.

### Inputs / Fields
- **Style:** Shared access fields use white fill, charcoal-violet text, 1px medium-gray stroke, and the control radius. Document-editor fields use the compact input token; labels remain above fields.
- **Focus:** Border changes to institutional red and a soft red ring appears; hover darkens the border.

### Navigation
- **Style:** White header separated from the warm-gray workspace by a thin rule. Brand wordmark sits left, navigation in the middle, and member identity/logout at the end.
- **State:** Muted links turn red on hover. The active link uses charcoal text and a 3px red underline.
- **Mobile:** Navigation occupies a second row; the identity text is hidden while logout remains available.

### Notices
- **Style:** Compact rounded blocks with 12px by 14px padding. Errors use the pale red/error pair; informational messages use the pale blue/blue pair.

### Document List Rows
- **Style:** Open rows separated by thin horizontal rules rather than cards. Type and metadata remain secondary to the document title; metadata moves beneath the title on narrow screens.

### Document Editor
- **Workspace panels:** White, softly rounded, bordered surfaces on the warm-gray ground. The authoring panel groups structured letter fields above Markdown; the adjacent preview panel presents the unsigned PDF and its download action.
- **Save action:** Uses the institutional primary button treatment at a compact workspace size. Saving is explicit; synchronized draft state does not itself allocate a letter identifier.
- **Responsive behavior:** At the workspace breakpoint, Edit and Preview become tabs. Keep the selected marker, visible focus, connection state, and save state clear. The academic page belongs inside the preview and is not application chrome.
- **Scope:** These patterns describe the shipped T12 editor, not a new global layout mandate. Broader visual refinement remains open for later manual work.

## Do's and Don'ts

### Do:
- **Do** use the institutional red token for primary actions and active navigation.
- **Do** keep form surfaces white against the warm-gray workspace ground.
- **Do** retain clear labels, visible keyboard focus, and the responsive stacking behavior.
- **Do** use only approved SCESI and UMSS marks when an institutional mark is needed.

### Don't:
- **Don't** recreate the academic PDF header in application chrome.
- **Don't** add emoji or substitute glyph icons for the approved icon approach.
- **Don't** treat the current implementation as a final visual settlement; broader refinement remains open for later manual work.
