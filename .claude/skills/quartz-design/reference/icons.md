# Icons

Inline SVG Vue components, one file per icon in `components/icons/`, no icon library. Lucide-style line icons.

```vue
<template>
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="3" y="11" width="16" height="11" rx="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
</template>
```
(`assets/icon-example.vue` is the lock icon in this form. Some older Quartz icons, e.g. the bolt, still lack the round caps and joins; use them for all new icons.)

Rules
- 24x24 viewBox, rendered at 16px everywhere (same size on every card); stroke 1.8, round caps and joins, no fill.
- Color via the parent: `class="text-chargepoint"`, `text-pv`, `text-muted`; never hard-code a color inside the SVG.
- Decorative icons get `aria-hidden="true"`; the button around an icon carries `aria-label` and `title`.
- Entity icons: bolt = charge point, car = vehicle, battery, house, sun = generation, counter (gauge), consumer (drop), cloud-sun = forecast.
- Action icons: gear = settings, lock / lock-open = lock (green open, red locked), pencil = edit, refresh = reload (spins with `animate-spin` while running), close, menu, chevrons.
- Spacing: icon + text `gap-1.5` to `gap-2`; icon buttons are round (26px, 22px small) with a 1px border.
