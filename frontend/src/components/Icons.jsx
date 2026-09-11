/** Inline SVGs. No icon library: five kilobytes of paths beats a dependency. */

const base = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

export const Icon = {
  shield: (p) => (
    <svg {...base} {...p}>
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" />
    </svg>
  ),
  pr: (p) => (
    <svg {...base} {...p}>
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="18" r="2.5" />
      <path d="M6 8.5v7" />
      <path d="M18 15.5V11a3 3 0 00-3-3h-4" />
      <path d="M13 5l-2 3 2 3" />
    </svg>
  ),
  review: (p) => (
    <svg {...base} {...p}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  ),
  chart: (p) => (
    <svg {...base} {...p}>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </svg>
  ),
  agents: (p) => (
    <svg {...base} {...p}>
      <circle cx="9" cy="8" r="3" />
      <circle cx="17" cy="10" r="2.5" />
      <path d="M3 20a6 6 0 0112 0" />
      <path d="M15 20a4.5 4.5 0 016-4" />
    </svg>
  ),
  settings: (p) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
    </svg>
  ),
  gauge: (p) => (
    <svg {...base} {...p}>
      <path d="M12 14l4-4" />
      <path d="M4 18a8 8 0 1116 0" />
    </svg>
  ),
  wrench: (p) => (
    <svg {...base} {...p}>
      <path d="M14.7 6.3a4 4 0 105.3 5.3L21 11l-8 8-1.5 1.5a2 2 0 01-2.8-2.8L10 16l-6-6a2 2 0 012.8-2.8L8 8.5z" />
    </svg>
  ),
  check: (p) => (
    <svg {...base} {...p}>
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  alert: (p) => (
    <svg {...base} {...p}>
      <path d="M12 9v4M12 17h.01" />
      <path d="M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
    </svg>
  ),
  file: (p) => (
    <svg {...base} {...p}>
      <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  ),
  trash: (p) => (
    <svg {...base} {...p}>
      <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
    </svg>
  ),
}
