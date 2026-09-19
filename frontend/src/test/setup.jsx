import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// Monaco needs web workers, ResizeObserver and layout APIs jsdom does not
// provide. The editor is not what these tests are checking, so it is replaced
// by a plain textarea that keeps the same value/onChange contract.
vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }) => (
    <textarea
      data-testid="code-editor"
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}))

// jsdom has no ResizeObserver; several layout paths touch it.
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// scrollIntoView is called after a review completes.
Element.prototype.scrollIntoView = vi.fn()
