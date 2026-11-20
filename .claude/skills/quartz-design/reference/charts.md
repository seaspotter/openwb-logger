# Charts (Chart.js 4 via vue-chartjs)

- Plugins used: `chartjs-adapter-luxon` (time axis), `chartjs-plugin-annotation`, `chartjs-plugin-zoom`.
- Canvas cannot use `var(--x)`: resolve tokens with `getCssColor('--pv')` (`assets/color.ts`) and rebuild on theme change.

## Lines
| Series | Style |
|---|---|
| Category total (area) | `borderWidth 1.25`, fill with `hexToRgba(color, 0.18)` |
| Individual instance | `borderWidth 1.25`, fill 0.12, shade of the category color via `instanceColor(base, index)` |
| Forecast | `borderWidth 1.5`, `borderDash [6, 6]`, no fill |
| SoC (battery, vehicle) | `borderWidth 1.5`, `borderDash [3, 3]`, no fill, on a second right-hand axis 0-100 % |

Always `pointRadius 0`, `tension 0.2`. Category colors are the entity tokens (pv green, grid red, battery yellow, car teal,
chargepoint blue, consumer violet, consumption slate).

## Axes and chrome
- Grid lines `color: var(--border)`; the right (SoC) axis has no grid.
- Ticks `color: var(--muted)`, 11px on the time axis, 12px on value axes, 10px below 640 px viewport width.
- Axis titles ("Leistung [kW]", "SoC [%]") 12px muted; hidden on narrow screens (they eat plot width).
- Built-in legend off. Own legend in the header row: borderless buttons (`text-[11px] text-muted`, `gap-1.5`) with a colored 10px `.legend-dot` before the label; click toggles the series, hidden series `opacity-40`.
- Chart card: `panel px-3 pt-5 pb-4 sm:px-6`; title `text-base font-bold` with a small muted pill (`rounded-full px-2.5 py-1 text-[13px] font-semibold badge-muted`) for the range switch (day/live).
- "Jetzt" marker: dashed vertical annotation line with a bold 11px muted label drawn manually above the plot area.
- Zoom: wheel/pinch zoom, resets after 5 minutes without interaction.

## Flow bar (not Chart.js)
Plain flex divs, see components.md.
