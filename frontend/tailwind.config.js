/** Design tokens for the dark UI. Palette values are fixed here rather than
 *  spread through className strings so a colour means one thing everywhere. */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces, darkest to lightest: page, sidebar, card, raised, border.
        ink: {
          950: '#080B14',
          900: '#0B1020',
          850: '#0F1528',
          800: '#141B31',
          700: '#1C2540',
          600: '#27314F',
        },
        brand: {
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,.3), 0 8px 24px -12px rgba(0,0,0,.5)',
        glow: '0 0 0 1px rgba(99,102,241,.35), 0 8px 32px -8px rgba(99,102,241,.35)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}
