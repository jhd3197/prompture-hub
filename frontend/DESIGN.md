# Prompture Hub dashboard: design system

Scope: the logged-in console (React 18, Vite, react-router, plain CSS tokens). No UI or chart libraries.
Charts, the command palette and the motion are hand-written SVG, CSS and small hooks.

## Phase 0: brief

- Subject: an LLM API gateway. It issues scoped hub keys (model allowlist, spend cap per day, week or month,
  rate limit), meters every call, falls back between providers, reconciles its own ledger with provider billing,
  and pairs companion devices.
- Audience: the one operator who runs the hub, usually checking "am I about to blow a cap" or "who spent that".
- Job: give the operator a reading in under three seconds, then let them act (pause, raise a cap, revoke, copy an id)
  without leaving the keyboard.
- Honesty rule: a chart shows only numbers the API returned. Where a number is derived (spend inside a cap
  window, projected burn), the label says how.

## Phase 1: concepts

| | A. Tape | B. Calibrated | C. Patch bay |
|---|---|---|---|
| Territory | material of billing (the ledger, receipt paper) | the discipline of metering (graduated scales, redlines, damped needles) | how the gateway works (keys patched to models, a fallback is a second cable) |
| Idea | Every request prints as a line on a running tape | Every figure sits on a graduated scale, so you read spend, caps and latency like bench instruments | The app is a switchboard: keys on the left, models on the right, cables between |
| Anchor | usage rows are append-only | caps are thresholds in a window, with 70% and 90% alarm points | a hub key maps to routes and fallbacks |
| Signature | the activity feed prints and the total ticks over | a ticked rule with a needle that settles on the reading | drag a cable to route |
| Originality / fit / feasibility / portability (lower is better) | 3 / 4 / 4 / 3 | 4 / 5 / 5 / 2 | 4 / 4 / 2 / 2 |

Pick B. It is the only one that styles the product's central object, a cap with alarm points, and it needs no
illustration. Steal one detail from C: on Models the route string is split `provider / model` with a patched dot.
A is the reason the activity table is mono, ruled and newest first.

### Concept card

```
Idea:        Calibrated. The hub is an instrument: every number sits on a graduated scale with its redline marked.
Metaphor:    Bench instruments. A ruler of ticks, alarm notches at 70% and 90%, a needle that is damped, not snapped.
Signature:   The rule. One tick scale used as the nav underline (with a needle that settles under the current page),
             the cap meter (notches at 70 and 90, projected burn as a ghost tick), chart axes and the page header.
Emotion:     Calm and exact. "I know how much headroom I have."
Motion verb: settle. Things travel to their reading with a small overshoot and come to rest. Never bounce twice.
Screenshot:  Keys: a column of cap meters, one amber at 74%, one red at 93%, tabular figures aligned right,
             the needle under "Keys" in the top rule.
```

### Genericness test

A generic model asked for "LLM gateway dashboard" lands on: dark sidebar, green accent, four equal stat cards, a line
chart in a card, a table. Changes made because of that answer:

- No sidebar. A top rule (nav tabs on a ticked line) plus a command palette is the navigation. Mobile gets a bottom tab bar.
- Stat tiles are a joined readout strip with mono figures, a sparkline each and a unit set small, not four cards.
- Panels are not identical: a panel head is a ticked label, meters and bar lists replace most "cards of text".
- The accent is a tool (needle, fill, focus), not a wash. Amber and red are reserved for thresholds.
- Home leads with the largest reading (24 h spend over a 7 day trace), then the keys closest to their caps.

## Phase 2: system

### Palette (OKLCH, accent hue stays user-selectable through `--accent-h`, theme through `data-theme`)

| Role | Light "bench paper" | Dark "graphite" | Use |
|---|---|---|---|
| ground | `oklch(.968 .003 255)` | `oklch(.145 .008 255)` | page |
| panel | `oklch(.996 .001 255)` | `oklch(.19 .009 255)` | panels, popovers |
| sunk | `oklch(.945 .004 255)` | `oklch(.16 .008 255)` | wells, table heads, inputs |
| ink | `oklch(.2 .015 260)` | `oklch(.96 .004 255)` | primary text |
| ink-2 | `oklch(.38 .015 260)` | `oklch(.82 .008 255)` | secondary text |
| ink-3 | `oklch(.48 .014 260)` | `oklch(.72 .01 255)` | captions and `.faint`, still AA on panel and ground |
| line / line-2 | `oklch(.9 .004 255)` / `oklch(.8 .006 255)` | `oklch(.28 .01 255)` / `oklch(.38 .012 255)` | hairlines, tick marks |
| accent | `oklch(.58 .15 h)` | `oklch(.78 .15 h)` | needle, fills, focus, primary action |
| accent-ink | `oklch(.45 .13 h)` | `oklch(.84 .12 h)` | accent used as text |
| amber | `oklch(.62 .14 65)` | `oklch(.8 .15 80)` | cap above 70%, caution |
| red | `oklch(.56 .2 25)` | `oklch(.72 .17 25)` | cap above 90%, errors |

Chart colour rules: marks that carry data are at least 3:1 against the panel. Series are told apart by position,
labels and pattern (the provider bar is outlined, the hub bar is filled), never by hue alone. Share charts use a
lightness ramp of the accent, not a rainbow. Amber and red keep fixed hues in both themes.

### Type

- Grotesk: Schibsted Grotesk (variable 400 to 800, self-hosted). Kept from the first pass: it is a newspaper grotesk with
  sturdy numerals and a slightly squared stance, which suits an instrument panel better than a geometric. Titles are
  800 at 30 px with -0.04em tracking, body 14 px at 1.5.
- Mono: Geist Mono (variable, self-hosted). It carries every figure, id, route and caption. Readouts are mono 500 at 34 to 40 px
  with -0.04em, with the unit set at 0.5em in ink-3.
- Captions: mono 11 px, uppercase, +0.06em, ink-3. Used for scale labels and panel heads only, never above every heading.
- Numbers use `tabular-nums` and `slashed-zero`. Right-align numeric columns.
- Fluid steps: title `clamp(26px, 1.4rem + .9vw, 34px)`, readout `clamp(30px, 1.6rem + 1.2vw, 44px)`.

### Grid and rhythm

- Page container 1320 px max, side margin `clamp(16px, 3vw, 40px)`. 12 columns, 24 px gutter (16 px on tablet).
- Spacing steps 4, 8, 12, 16, 24, 32, 48, 64. Section gaps are 24 (tight, inside a story), 40 (between stories).
  Page head is 40 px from the bar, readout strip is flush under the head, secondary panels hang off columns 1-8 and 9-12.
- Top bar 52 px, sticky. Table headers stick at 52 px.
- Mobile: 4 columns, bottom tab bar 56 px plus safe area, panels full-bleed edge to edge with hairlines.

### Shape

One radius rule: 6 px for controls and panels, 10 px for overlays (palette, modals), pills only for status dots. Hairlines first;
shadows only for things that float (menus, palette, modal, toast).

### Motion language (verb: settle)

- Eases: `--settle: cubic-bezier(.22, 1.2, .36, 1)` (one small overshoot, used for transforms of needles, meters, press release);
  `--glide: cubic-bezier(.2, .8, .2, 1)` (no overshoot, used for fades, panels, palette).
- Durations: press 120 ms, hover 160 ms, panel entry 420 ms with 45 ms stagger, chart draw 700 ms, meter fill 800 ms,
  count-up 700 ms, route change 320 ms.
- Only `transform`, `opacity` and `clip-path` animate. Count-ups change text, inside a ghost that holds the final width.
- Feedback: buttons lift 1 px on hover and press down 1 px with a settle release; nav tabs move the needle; rows draw a left tick
  (`scaleY`) on hover and focus; meters re-settle when a cap is edited.
- Idle: the live dot in the bar breathes (scale and opacity), and the needle rests on the current page. Nothing else loops.
- Reduced motion: every animation is removed (`animation: none`), content is visible in its final state, count-ups render the final value,
  the needle jumps, skeleton shimmer is a static tint.

### Composition by page

```
Home          head | readout strip: [24h spend + 7d trace][active keys][calls + error share]
              keys near their cap (meters)  |  activity table (full width, sticky head, chips never clip)
Analytics     head + range | readout strip (5) | spend and requests trace (tabs: chart / table) | latency trace + errors
              by model (bars + p50..p95 range) | by provider share | by key | recent errors
Billing       head + period + refresh | delta bars (hub vs provider) | status table with notes
Keys          head | toolbar (search, density) | table: name, scope, cap meter, rate, state, row menu | cards under 760 px
Create key    two columns: form sections | sticky "policy preview" meter
Sessions      list (left) + transcript (right), cost per message as tick bars
Models        provider groups with route strings, capability filters
Pair          code entry as segmented readout, review, result
Settings      left rule nav (tabs on mobile), each sub page a stack of panels
Login         split: calibrated hero with the trust flow, right sign-in
```

## Command palette and keyboard

- `Cmd/Ctrl+K` or `/` opens the palette (combobox + listbox). Groups: Pages, Actions, Keys, Sessions. Fuzzy match on label and keywords.
- `g` then a letter: h home, a analytics, b billing, k keys, c sessions, m models, p pair, s settings. `c` alone creates a key. `?` shows the sheet.
- Dialogs trap focus, close on Escape, restore focus to the opener.

## Content rules

Sentence case, no em or en dashes, no filler verbs, no fake metrics, no decorative numbering. Empty states say what will appear and give the next action.

## Decisions and known limits

- Idle: the page is still at rest by decision. Only the live dot in the bar breathes and the brand needle twitches every seven seconds;
  data surfaces do not loop. Hover, press and focus answer in the settle verb everywhere (lift, press, tick draw).
- Removed in the last pass: the gradient wash behind the hero readout. The rule, needle and notches carry the identity.
- Fonts stay Schibsted Grotesk and Geist Mono from the first pass (self-hosted, preloaded, metric-matched fallbacks).
- Pair and Create key no longer autofocus a field, so the skip link stays the first tab stop.

- No per-device usage exists in the API, so Devices shows last-seen position on a 30 day scale and nothing invented.
- Per-key spend inside the cap window is derived from `/api/analytics` (day window = today in UTC, week = since Monday UTC, month = since the 1st UTC).
  It excludes manual spend adjustments, and the UI says so.
- Per-route HTML, robots.txt, sitemap and 404 status codes belong to the backend; the SPA ships a static shell in `index.html`.
