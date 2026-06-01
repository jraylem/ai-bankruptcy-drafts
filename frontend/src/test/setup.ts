import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

class TestStorage implements Storage {
  private store = new Map<string, string>()

  get length() {
    return this.store.size
  }

  clear() {
    this.store.clear()
  }

  getItem(key: string) {
    return this.store.get(String(key)) ?? null
  }

  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string) {
    this.store.delete(String(key))
  }

  setItem(key: string, value: string) {
    this.store.set(String(key), String(value))
  }
}

Object.defineProperty(globalThis, 'Storage', {
  configurable: true,
  value: TestStorage,
  writable: true,
})

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: new TestStorage(),
  writable: true,
})

Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: globalThis.localStorage,
})

afterEach(() => {
  cleanup()
})
