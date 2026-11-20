/** Format a power value already in kW: below 1 kW in W ("850 W"), otherwise in kW with 3 decimals ("6,400 kW"). */
export function formatKw(kw: number): string {
  const watts = Math.round(kw * 1000) || 0 // || 0 turns -0 into 0
  if (Math.abs(watts) < 1000) return `${watts.toLocaleString()} W`
  return `${kw.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })} kW`
}

/** Format a price in ct/kWh, e.g. 21.4 -> "21,4 ct". */
export function formatCentsPerKwh(cents: number): string {
  return `${cents.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ct`
}

/** Format an energy value already in kWh, e.g. 6.4 -> "6,400 kWh" (3 decimals by default, matching formatKw). */
export function formatKwh(kwh: number, decimals = 3): string {
  return `${kwh.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} kWh`
}

/** Format a runtime duration already in seconds, e.g. 5400 -> "1:30 h". */
export function formatRuntime(seconds: number): string {
  const totalMinutes = Math.floor(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}:${String(minutes).padStart(2, '0')} h`
}
