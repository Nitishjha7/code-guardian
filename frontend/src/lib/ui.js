/** Shared visual vocabulary. One place, so severity never means two things. */

export const BAND = {
  critical: {
    label: 'Critical Risk',
    ring: '#f43f5e',
    text: 'text-rose-300',
    chip: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
  },
  high: {
    label: 'High Risk',
    ring: '#fb923c',
    text: 'text-orange-300',
    chip: 'border-orange-500/40 bg-orange-500/10 text-orange-300',
  },
  medium: {
    label: 'Medium Risk',
    ring: '#fbbf24',
    text: 'text-amber-300',
    chip: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  },
  low: {
    label: 'Low Risk',
    ring: '#38bdf8',
    text: 'text-sky-300',
    chip: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  },
  none: {
    label: 'No Issues',
    ring: '#34d399',
    text: 'text-emerald-300',
    chip: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  },
  unknown: {
    label: 'Unknown',
    ring: '#64748b',
    text: 'text-slate-400',
    chip: 'border-slate-600 bg-slate-800 text-slate-400',
  },
}

export const SEVERITY = {
  Critical: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
  High: 'border-orange-500/40 bg-orange-500/10 text-orange-300',
  Medium: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  Low: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
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
export const CARD =
  'rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm'
