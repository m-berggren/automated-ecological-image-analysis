/**
 * Shared frontend configuration.
 *
 * All values read from Vite env vars with sensible dev defaults.
 * Override via .env or .env.local:
 *   VITE_API_BASE_URL=https://api.example.com
 *   VITE_UPLOAD_CONCURRENCY=6
 */

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const UPLOAD_CONCURRENCY: number =
  Number(import.meta.env.VITE_UPLOAD_CONCURRENCY) || 4
