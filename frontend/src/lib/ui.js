/** Shared visual vocabulary. One place, so severity never means two things. */

export const BAND = {
  critical: {
    label: 'Critical Risk',
    ring: '#f43f5e',
    text: 'text-rose-300',
    chip: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
  },
  high: {
    label: 'High Risk',
    ring: '#fb923c',
    text: 'text-orange-300',
    chip: 'border-orange-500/30 bg-orange-500/10 text-orange-300',
  },
  medium: {
    label: 'Medium Risk',
    ring: '#fbbf24',
    text: 'text-amber-300',
    chip: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  },
  low: {
    label: 'Low Risk',
    ring: '#38bdf8',
    text: 'text-sky-300',
    chip: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  },
  none: {
    label: 'No Issues',
    ring: '#34d399',
    text: 'text-emerald-300',
    chip: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  },
  unknown: {
    label: 'Unknown',
    ring: '#64748b',
    text: 'text-slate-400',
    chip: 'border-ink-600 bg-ink-700 text-slate-400',
  },
}

export const SEVERITY = {
  Critical: BAND.critical.chip,
  High: BAND.high.chip,
  Medium: BAND.medium.chip,
  Low: BAND.low.chip,
}

export const band = (name) => BAND[name] || BAND.unknown

export const LANGUAGES = [
  'python',
  'javascript',
  'typescript',
  'java',
  'go',
  'sql',
  'css',
  'html',
  'json',
]

/** Card shell used everywhere, so spacing and borders stay consistent. */
export const CARD = 'rounded-xl border border-ink-700 bg-ink-850 shadow-card'

export const BTN_PRIMARY =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm ' +
  'font-medium text-white transition hover:bg-brand-500 disabled:cursor-not-allowed ' +
  'disabled:opacity-40'

export const BTN_GHOST =
  'inline-flex items-center justify-center gap-2 rounded-lg border border-ink-700 ' +
  'bg-ink-800 px-3.5 py-2 text-sm text-slate-300 transition hover:border-ink-600 ' +
  'hover:bg-ink-700 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40'
