---
name: SCESI Letter
description: Institutional access and navigation for an academic correspondence workspace.
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
rounded:
  control: "7px"
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
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "12px 18px"
    height: "50px"
  input-text:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 13px"
    height: "50px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.institutional-dark}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "42px"
---

# Design System: SCESI Letter

## Overview

**Creative North Star: “Geometría institucional”**

The shipped access and navigation slice uses a clear institutional frame: a broad red identity field beside a quiet white form, followed after sign-in by a light workspace shell. Onest carries both prominent Spanish headings and everyday controls. The supplied SCESI and university marks remain the authority for institutional identity; the application adds only a small crossing-line pennant cue.

This record describes the implemented T11 access and navigation surface. The broader product design remains open for the user’s manual refinement; this document does not settle future editor, document, or organization surfaces.

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

Desktop access uses a two-column frame, with the identity region wider than the form region. The form stays within a 420px inner width. At 900px, the split narrows and authenticated navigation moves to a second header row; at 680px, access stacks identity above the form and the authenticated header retains navigation below its brand/account row. The workspace content is centered at up to 1120px with 20–24px minimum side gutters. At narrow widths, document rows stack their metadata under the main text.

Spacing is a compact 2, 8, 12, 20, and 24px rhythm, with larger section gaps and responsive outer padding where needed. Reduced-motion preferences shorten transitions and animations.

## Elevation & Depth

Surfaces are flat at rest. White and warm gray establish the main surface separation, with thin rules for structure. Focus is the one elevated treatment: a three-pixel translucent red ring around fields, paired with a strong visible outline for keyboard focus.

### Shadow Vocabulary
- **Field focus ring** (`0 0 0 3px rgb(164 0 0 / 18%)`): Draws attention to the active text field.

### Named Rules
**The Flat Surface Rule.** Use surface color and fine separators for structure; reserve the soft ring for an actively focused field.

## Shapes

Controls use gently rounded corners (7px). The overall form language is rectangular and crisp, with thin borders on fields and no decorative card grid.

## Components

### Buttons
- **Character:** Compact, direct actions with clear primary and quiet treatments.
- **Shape:** Control radius (7px).
- **Primary:** Institutional red fill, white semibold text, 50px minimum height, and 12px by 18px padding. Hover darkens and lifts by 1px; active returns to rest; disabled communicates waiting with reduced opacity.
- **Quiet:** Transparent background, dark red text, 42px minimum height; hover adds a pale red surface and border.
- **Focus:** Keyboard focus receives a visible 3px outline with offset.

### Inputs / Fields
- **Style:** White fill, charcoal-violet text, 1px medium-gray stroke, 7px radius, 50px minimum height, and 11px by 13px padding. Labels sit above the field.
- **Focus:** Border changes to institutional red and a soft red ring appears; hover darkens the border.

### Navigation
- **Style:** White header separated from the warm-gray workspace by a thin rule. Brand wordmark sits left, navigation in the middle, and member identity/logout at the end.
- **State:** Muted links turn red on hover. The active link uses charcoal text and a 3px red underline.
- **Mobile:** Navigation occupies a second row; the identity text is hidden while logout remains available.

### Notices
- **Style:** Compact rounded blocks with 12px by 14px padding. Errors use the pale red/error pair; informational messages use the pale blue/blue pair.

### Document List Rows
- **Style:** Open rows separated by thin horizontal rules rather than cards. Type and metadata remain secondary to the document title; metadata moves beneath the title on narrow screens.

## Do's and Don'ts

### Do:
- **Do** use the institutional red token for primary actions and active navigation.
- **Do** keep form surfaces white against the warm-gray workspace ground.
- **Do** retain clear labels, visible keyboard focus, and the responsive stacking behavior.
- **Do** use only approved SCESI and UMSS marks when an institutional mark is needed.

### Don't:
- **Don't** recreate the academic PDF header in application chrome.
- **Don't** add emoji or substitute glyph icons for the approved icon approach.
- **Don't** treat the current access layout as a settled direction for the broader product; future visual refinement remains open.
