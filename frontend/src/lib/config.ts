/**
 * Shared frontend configuration.
 *
 * All values read from Vite env vars with sensible dev defaults.
 * Override via .env or .env.local:
 *   VITE_API_BASE_URL=https://api.example.com
 *   VITE_UPLOAD_CONCURRENCY=6
 */

// An explicitly empty VITE_API_BASE_URL means "same origin" (relative URLs),
// used by the nginx Docker stack. Only an unset var falls back to the dev API.
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
export const API_BASE_URL: string =
  apiBaseUrl === undefined ? 'http://localhost:8000' : apiBaseUrl

export const UPLOAD_CONCURRENCY: number = Number(import.meta.env.VITE_UPLOAD_CONCURRENCY) || 4
