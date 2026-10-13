# UI Specification

Companion to `docs/PRD.md` (section 14). Visual source of truth is the design canvas:
https://claude.ai/artifact/25hwnVHsfUirQYJ4iR9o3t

Implement with Next.js, Tailwind CSS and shadcn/ui. Expose every token below as a CSS variable and map it in the Tailwind theme, so light and dark share the same component code. Never hard-code a hex value in a component.

---

## 1. Design language

Calm and comfortable, not decorative. A warm neutral ground, white working surfaces with soft depth, one indigo for human actions and one teal for everything the agent does. Generous spacing and readable type. Speed over ornament.

**Layout (web):** left sidebar on the ground color, main content in a white rounded panel (20 px radius) floating on the ground, optional right panel on the ground containing white cards. 8 px outer padding and 8 px gaps between zones.

**Layout (mobile, 390 px reference):** single column, top bar, content, bottom tab bar (Chat, Tasks, Docs, Agent). Review and detail flows open as bottom sheets.

---

## 2. Color tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `ground` (G0) | `#F5F4F1` | `#171A21` | Board columns, list backgrounds |
| `sidebar` (SB) | `#EBE9E4` | `#0F1115` | App background behind panels |
| `surface` (S) | `#FFFFFF` | `#1C1F27` | Panels, cards |
| `surface-2` (S2) | `#FAF9F7` | `#191C23` | Card footers, inputs, subtle blocks |
| `ink` | `#1F2430` | `#ECEEF3` | Primary text |
| `ink-2` | `#3E4452` | `#C9CDD7` | Body text |
| `muted` | `#666B77` | `#9BA1AE` | Secondary text |
| `line` | `#E7E5DF` | `#2A2E38` | Dividers |
| `brand` | `#4B4ACF` | `#5B5AE0` | Primary actions, links, selection |
| `brand-tint` / `brand-text` | `#ECECFB` / `#3B3AB5` | `#25254A` / `#B9B8FA` | Selected states, chips |
| `agent` | `#0E7C6B` | `#148572` | Agent avatar and agent-originated UI |
| `agent-tint` / `agent-text` / `agent-border` | `#E3F3EF` / `#0A6154` / `#BFE2DA` | `#153631` / `#7ED6C6` / `#2A5A52` | Proposed state, agent answers |
| `success` / tint | `#1B7A46` / `#E4F4EA` | `#5BC98A` / `#173525` | Completed, online, low risk |
| `warning` / tint | `#8A5200` / `#FCEFD6` | `#F0B35A` / `#3A2D14` | High risk, offline, admin only |
| `danger` / tint / border | `#B42318` / `#FDECEA` / `#F3C7C1` | `#FF8A7C` / `#3D1E1B` / `#6B2F29` | Reject, delete, never |
| `chip` (CH) | `#E4E1DA` | `#262A33` | Neutral chips, toggles off |
| avatar 1 / 2 / 3 | `#F0C9B6` / `#BBD0F0` / `#D5D3F7` | `#8A5F4A` / `#3E5A8C` / `#5A58A8` | Member avatars |
| `ring` | `rgba(31,36,48,.09)` | `rgba(255,255,255,.09)` | 1 px card outline (box-shadow, not border) |
| `shadow` | `rgba(31,36,48,.06)` | `rgba(0,0,0,.35)` | Soft elevation |
| `scrim` | `rgba(31,36,48,.45)` | `rgba(0,0,0,.6)` | Behind sheets and dialogs |

All text and control colors meet WCAG AA contrast on their intended backgrounds. Do not use `muted` below 12 px.

---

## 3. Typography

| Role | Font | Notes |
|---|---|---|
| UI and body | Figtree 400/500/600/700 | Body 15 px, line-height 1.5 to 1.6 |
| Headings and wordmark | Bricolage Grotesque 600/700 | Page titles 26 to 38 px, card titles 18 to 22 px |
| IDs and code | JetBrains Mono 400/500 | `BUG-58`, filenames, JSON |

Scale: 12 (labels, chips, timestamps), 13 (secondary), 14 (controls, table cells), 15 (body), 17 (document body), 18 to 22 (card and section titles), 26 to 38 (page titles), 44 to 68 (landing hero only). Minimum text size is 12 px. Use `overflow-wrap: anywhere` so long names never break layouts.

---

## 4. Shape, depth, spacing

- Radius: 8 (tags), 10 to 12 (controls), 14 to 16 (cards), 20 (main panels), 24 (marketing cards, mobile sheets), 999 (chips, avatars).
- Cards use a 1 px **ring shadow** plus a soft shadow, never a solid border: `box-shadow: 0 0 0 1px ring, 0 4px 16px shadow`. Dividers inside cards use `line`.
- Spacing steps: 4, 8, 12, 16, 20, 24, 32, 40, 48. Page padding 24 to 32 (web), 16 (mobile).

---

## 5. Components

**Buttons** (min height 44 px, radius 12, weight 600)
- Primary: `brand` fill, white text. Secondary: `surface`, ring shadow. Danger: `surface`, danger text, danger border ring. Disabled: `chip` fill, `muted` text.
- Pressed state on every button and tappable link: `transform: scale(.97)`.

**Chips:** pill, 12 px, weight 600, tint background with matching text color. Priority chips include a flag icon. Never rely on color alone: always include the label.

**Proposal card (core component):** header with agent avatar, "Proposed task", state chip and risk chip; body with title, property pills (Type, Priority, Owner, Project, Due), steps, and a "Based on" row of source chips; footer on `surface-2` with explanatory text and actions (Reject, Edit, Approve and create). On mobile the footer stacks: full-width primary, then Edit and Reject side by side. State chip values: `Proposed`, `Approved`, `Completed`, `Rejected`, `Failed`. Risk labels: `Low risk`, `High risk` (shown with who can approve: "any Editor can approve", "only an Admin can approve").

**Agent steps pill:** collapsed single line ("Read 12 messages, searched memory, drafted a proposal") expandable to the tool-call list.

**Inputs:** radius 12, min height 48, inset shadow plus ring, 16 px font on touch devices (prevents iOS zoom). Every input has a visible label.

**Toggles:** 48 x 28, `role="switch"`, `aria-checked`, label required.

**Tables:** CSS grid rows, 12 px muted header, `line` dividers, 44 px minimum row height on touch.

**Bottom sheet (mobile):** 24 px top radius, 40 x 4 drag handle, scrim behind, safe-area bottom padding.

**Empty and error states:** icon in a `chip` circle, one-sentence explanation, one primary action. The "No access" state states plainly that the agent cannot read what the user cannot.

---

## 6. Motion (follow Emil Kowalski's design-engineering rules)

- Animate only `transform` and `opacity`. Never `transition: all`.
- Easing: enter and exit use `cubic-bezier(0.23, 1, 0.32, 1)`; sheets and drawers use `cubic-bezier(0.32, 0.72, 0, 1)`. Never `ease-in` on UI.
- Durations: press feedback 160 ms, proposal card entrance 220 ms, sheets 320 ms. UI motion stays under 300 ms except sheets.
- Nothing enters from `scale(0)`: start at 0.98 with opacity 0 and a small translate.
- Do not animate anything used constantly or triggered by keyboard (navigation, command palette, shortcuts).
- Use transitions, not keyframes, for interruptible UI. The typing indicator is the only looping animation.
- Hover styles only inside `@media (hover: hover) and (pointer: fine)`.
- `prefers-reduced-motion`: remove transforms and loops, keep opacity and color changes.

---

## 7. Mobile rules (feel native)

- Viewport: `width=device-width, initial-scale=1, viewport-fit=cover`. Never disable zoom.
- Use `100dvh` for the app shell and `env(safe-area-inset-*)` for the tab bar, sheets and fixed bars.
- `-webkit-tap-highlight-color: transparent`; `touch-action: manipulation` on controls; `user-select: none` on controls only (never on content).
- `overscroll-behavior: none` on the root and `contain` on inner scroll areas.
- Inputs are at least 16 px. Touch targets at least 44 px.
- In chat, the latest content stays pinned to the bottom above the composer.
- Test on a real device, with the keyboard open, in landscape once.

---

## 8. Accessibility

Visible focus ring on every interactive element (2 px `brand`, offset 2 px). Full keyboard navigation. Semantic landmarks (`nav`, `main`, `aside`, `header`), `role="tablist"` for tabs, `role="dialog"` for sheets and modals, `role="status"` for the offline banner, `aria-current="page"` on active navigation. Dark mode follows the OS setting with a manual override.

---

## 9. Screen inventory (design canvas titles)

Public: Landing, Pricing, Mobile landing.
Auth and first run: Sign up, Log in, Forgot password, Accept invitation, No access, Getting started, Mobile log in.
Core app (web): Channel with agent proposal (light and dark), Task board with detail, Task table, Document with Suggestions, Thread, Inbox, Search, Onboarding.
Core app (mobile): Channel (light and dark), Board, Agent and approvals sheet, Document offline, Inbox, Search, Thread.
Settings and billing: General, Members and roles, Agent, Memory, Audit log, Notifications, Profile and security, Plan and billing, Checkout. Mobile: Settings, Members, Billing.

Names, plan prices and numbers in the designs are sample content. The product name "Tandem" is a working name.
