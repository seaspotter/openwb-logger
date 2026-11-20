# Component recipes (Tailwind classes as used in Quartz)

Full files are in `../assets/`. The classes below are the contract.

## Card (`.panel`)
`.panel` = `rounded-[14px] border border-border bg-panel`. Entity card: `panel px-4 py-3`.
Header: `mb-2.5 flex items-center justify-between`; left `flex items-center gap-2` with a 16px icon (`text-<entity>`) and
`<span class="text-[14px] font-bold">`; right `flex items-center gap-1` with icon buttons and a `.badge`.
Inner block (selects, mode switches): `rounded-lg bg-bg px-2 py-1.5` (or `p-3`).

## Stat row (bottom of a card)
`mt-3 flex flex-wrap items-end gap-x-2 gap-y-2 text-xs`; each stat is a `StatBlock`: muted label, bold value below. Give each
block a fixed `min-w-[..rem] flex-none` so the row keeps its columns.

## Stat chip (top strip)
`panel flex flex-1 items-center justify-center gap-1.5 px-2 py-1.5 sm:px-[11px] sm:py-2`; icon in the entity color;
label `text-[10px] sm:text-[11px] text-muted`, value `text-xs sm:text-sm font-bold`; optional small arrow for flow direction.
Warning/error: `.chip-warning` / `.chip-error` (colored border + 12% tint). Clickable chips get `hover:border-accent`.

## Flow bar
Legend row: `text-[11px] sm:text-[13px]`, 10px rounded dot (`.legend-dot`), bold colored value, muted label.
Bar: `h-[26px] flex overflow-hidden rounded-lg`, segment widths in percent, colors from the entity tokens.
Two bars (sources, sinks) with a small arrow between them.

## Buttons
- Pill tab group: `rounded-full border`, active `border-accent bg-accent text-white`, inactive `border-border bg-transparent text-text`,
  `px-2.5 py-1.5 text-xs sm:px-[14px] sm:py-[7px] sm:text-[13px]`; `dense` variant `px-[9px] py-1 text-xs`.
- Button: `rounded-full border px-[11px] py-[5px] text-xs`; primary `bg-accent border-accent text-white`, secondary transparent,
  danger `border-grid text-grid`; disabled `opacity-40`.
- Icon button: `rounded-full border border-border`, 26px (22px `sm`); active `border-accent bg-accent text-white`;
  `tone="ok"` green tint, `tone="error"` red tint (lock open/closed).
- Toggle: `h-6 w-11 rounded-full`, off `#d1d5db`, on `bg-accent`, white knob that slides `translate-x-5`.

## Badges and status
`.badge` = `rounded-full px-[9px] py-[3px] text-[11px] font-bold whitespace-nowrap`. Variants (`.badge-ok|wait|error|muted`):
18% tint of pv / chargepoint / error, muted = `bg-bg text-muted`. Meaning: ok = charging/running, wait = plugged/ready, error = locked/fault, muted = idle.
Status boxes: `rounded-[10px] px-4 py-3 text-[13px]` with a 10-12% tint (`.status-box`, `-info`, `-warning`, `-fault`).

## Modal
Overlay `fixed inset-0 bg-[rgba(10,12,16,0.5)]`, content `.panel px-4 py-4 sm:px-7 sm:py-6` with `width: min(520px, 100%)`,
max height 90-94vh, scroll inside. Title `text-[15px] sm:text-[17px] font-bold`, close = round icon button top right.
Popover: small `.panel` anchored under its trigger (`top-[calc(100%+8px)] right-0`), `p-2`/`p-3`.

## Forms (`theme.css`)
`.field-label` (12px semibold muted), `.field-select` (`rounded-lg border bg-bg px-2.5 py-2 text-[13px]`), range inputs use
`accent-accent`, `.toggle-row` for label + toggle lines with a top border.

## Navigation
Top bar: `flex flex-wrap items-center justify-between gap-4 border-b border-border py-5`; brand 18px bold, optional centered clock
15px semibold muted, right side: connection indicator, user widget, round menu button with a popover menu (items `rounded-lg px-3 py-2 text-sm`).
