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
  // Shield with the bolt, matching the brand mark.
  shield: (p) => (
    <svg {...base} {...p}>
      <path d="M12 3l7.5 3v5.3c0 4.8-3.2 8.9-7.5 10.7C7.7 20.2 4.5 16.1 4.5 11.3V6L12 3z" />
      <path d="M12.9 8.2l-3.2 4.6h2.6l-1.2 3.6 3.2-4.7h-2.6l1.2-3.5z" fill="currentColor" strokeWidth="1" strokeLinejoin="round" />
    </svg>
  ),
  // Branch curving off a trunk, as in the PR mark.
  pr: (p) => (
    <svg {...base} {...p}>
      <circle cx="7" cy="18.5" r="2.6" fill="currentColor" stroke="none" />
      <circle cx="17" cy="7" r="2.6" fill="currentColor" stroke="none" />
      <path d="M7 15.9V4" strokeWidth="2" />
      <path d="M14.6 7.4c-2.6 0-2.2 2.6-3.8 3.9-1 .8-2.3 1-3.8 1" strokeWidth="2" />
    </svg>
  ),
  // A magnifier over a page of code.
  review: (p) => (
    <svg {...base} {...p}>
      <path d="M13.5 20H6a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v2.2" />
      <path d="M13 3v5h5" />
      <circle cx="15.5" cy="15.5" r="3.6" />
      <path d="M18.2 18.2L21 21" />
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
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path d="M12 8V4.5M9.5 3.2h5" />
      <circle cx="9" cy="14" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="15" cy="14" r="1.2" fill="currentColor" stroke="none" />
      <path d="M2 13v3M22 13v3" />
    </svg>
  ),
  settings: (p) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.6 1.6 0 00.33 1.77l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.6 1.6 0 00-1.77-.33 1.6 1.6 0 00-1 1.47V21a2 2 0 11-4 0v-.1A1.6 1.6 0 008.1 19.4a1.6 1.6 0 00-1.77.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.6 1.6 0 003.83 15a1.6 1.6 0 00-1.47-1H2a2 2 0 110-4h.1A1.6 1.6 0 003.6 8.9a1.6 1.6 0 00-.33-1.77l-.06-.06a2 2 0 112.83-2.83l.06.06A1.6 1.6 0 009 4.6a1.6 1.6 0 001-1.47V3a2 2 0 114 0v.1a1.6 1.6 0 001 1.47 1.6 1.6 0 001.77-.33l.06-.06a2 2 0 112.83 2.83l-.06.06A1.6 1.6 0 0019.4 9v0a1.6 1.6 0 001.47 1H21a2 2 0 110 4h-.1a1.6 1.6 0 00-1.47 1z" />
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
  github: (p) => (
    <svg {...base} fill="currentColor" stroke="none" viewBox="0 0 16 16" {...p}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  ),
  code: (p) => (
    <svg {...base} {...p}>
      <path d="M9 18l-6-6 6-6M15 6l6 6-6 6" />
    </svg>
  ),
  upload: (p) => (
    <svg {...base} {...p}>
      <path d="M12 16V4m0 0L8 8m4-4l4 4M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2" />
    </svg>
  ),
  clock: (p) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  ),
  sparkle: (p) => (
    <svg {...base} {...p}>
      <path d="M12 3l1.8 4.9L19 9.7l-5.2 1.8L12 16.4l-1.8-4.9L5 9.7l5.2-1.8L12 3z" />
      <path d="M18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" />
    </svg>
  ),
  copy: (p) => (
    <svg {...base} {...p}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 012-2h10" />
    </svg>
  ),
  refresh: (p) => (
    <svg {...base} {...p}>
      <path d="M3 12a9 9 0 0115.3-6.4L21 8M21 4v4h-4M21 12a9 9 0 01-15.3 6.4L3 16M3 20v-4h4" />
    </svg>
  ),
  chevron: (p) => (
    <svg {...base} {...p}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  ),
  branch: (p) => (
    <svg {...base} {...p}>
      <circle cx="7" cy="6" r="2.5" />
      <circle cx="7" cy="18" r="2.5" />
      <circle cx="17" cy="8" r="2.5" />
      <path d="M7 8.5v7M17 10.5c0 4-4 3-7 5" />
    </svg>
  ),
}
