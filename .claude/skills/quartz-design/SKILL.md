---
name: quartz-design
description: The Quartz look (openWB web theme) as a reusable style set - colors, typography, spacing, cards, chips, buttons, icons, charts, number formatting, dark mode. Use when building or restyling any UI that should look like Quartz.
---

# Quartz design language

Flat, calm, data-first dashboard UI. Light/dark, no UI framework, Tailwind v4 + CSS variables.
Source of truth: `assets/theme.css` (tokens + component classes) and the component files in `assets/`.
Details: `reference/components.md`, `reference/charts.md`, `reference/icons.md`.

## Stack
Vue 3 (`<script setup lang="ts">`), Vite, Tailwind CSS v4 (`@tailwindcss/vite`), Pinia, Chart.js 4 (`vue-chartjs`),
ESLint + Prettier. No component library, no icon library, no web fonts.

## Start a new project with this look
1. Copy `assets/theme.css` to `src/assets/css/theme.css`, import it in `main.ts` (it already has `@import 'tailwindcss'`).
2. Copy the `Base*.vue` components, `color.ts` and `format.ts` you need.
3. Dark mode: set `document.documentElement.setAttribute('data-theme', 'dark' | 'light')`; the tokens switch via `:root[data-theme='dark']`.

## Palette (tokens, all via CSS variables, never hard-coded in components)
| Token | Light | Dark | Meaning |
|---|---|---|---|
| bg / panel / border | #f1f2f4 / #fff / #e3e5e9 | #0a0b0d / #1f232b / #343a46 | page / card / 1px lines |
| text / muted | #1a1d24 / #6b7280 | #e7e9ee / #9aa0ac | |
| accent | #2563eb | (same) | primary action, active tab |
| pv | #1f9d55 | #3ec776 | generation, ok |
| grid | #dc2626 | #f87171 | grid / counters, danger |
| chargepoint | #2563eb | #5b9bff | charge points |
| battery | #eab308 | #facc15 | batteries |
| car | #0d9488 | #2dd4bf | vehicles |
| consumption | #475569 | #a7b0bf | house load |
| consumer | #7c3aed | #a78bfa | consumers |
| warning / error | #ea580c / #e11d48 | #fb923c / #fb7185 | |

Rule: one fixed color per entity type, used for its icon, chart line, legend dot and chip. Tinted backgrounds are the
token mixed into transparent (`color-mix(in srgb, var(--x) 12%, transparent)`), never a new color.

## Typography
- Font: `-apple-system, 'Segoe UI', Roboto, sans-serif` (system stack).
- Scale (px): 10-11 micro labels, 12 stats/buttons, **13 body and controls**, 14 card titles, 15 nav clock / modal title,
  17 modal title (sm+), 18 brand. Weights: 700 values and titles, 600 emphasis, 500 nav items, 400 text.
- Group labels: 11px, bold, uppercase, tracking 0.02em, muted (`.settings-group-label`).
- Labels are `text-muted`, values directly below or beside them are `font-bold`.

## Shape and spacing
- Flat: cards are `1px` border + `rounded-[14px]`, no shadows (only the toggle knob has one).
- Inner blocks: `rounded-lg`/`rounded-[10px]` on `bg-bg`. Controls (buttons, tabs, badges, icon buttons) are **fully round**.
- Page: `mx-auto max-w-7xl px-3 sm:px-6`, sections `mb-6`, card grid `grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4`.
- Card: `px-4 py-3`, header row `mb-2.5 flex items-center justify-between` (icon + 14px bold title left, round icon buttons + badge right).
- Mobile first: drop to smaller text/padding below `sm` (640px); the layout has no horizontal page scroll.

## Components (see reference/components.md)
Stat chips row, flow bar, entity cards, stat rows, round icon buttons (22/26px, tones ok/error), pill tab group, pill buttons
(primary/secondary/danger), toggle switch, status badges, status boxes, modal, popover, history chart.

## Icons
Inline SVG components, 24 viewBox, shown at 16px, `stroke="currentColor"`, width 1.8, round caps and joins, no fill
(Lucide-style). Color comes from the parent via `text-<entity>` classes. See reference/icons.md.

## Charts
Chart.js lines at 1.25-1.5px, no points, light fill, system chart chrome from the tokens, custom HTML legend. See reference/charts.md.

## Number formatting (German locale via `toLocaleString(undefined, ...)`)
- Power: below 1000 W in W, otherwise kW with 3 decimals ("850 W", "6,400 kW"). Energy kWh 3 decimals, 1 decimal on compact cards.
- Prices ct/kWh with 1 decimal. Non-breaking space before units. Empty value: "–". Helpers in `assets/format.ts`.

## Conventions
- UI text German. Keep code comments short and only for the non-obvious why.
- Entity colors and icons are the same everywhere (chips, cards, chart, popups).
- Quartz is GPL-3.0-or-later: copying its files verbatim carries that license; reimplementing the tokens and rules does not.
