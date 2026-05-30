# frontend

Vue 3 + TypeScript single-page app. It is a pure REST client: it owns no
business logic, only talks to the Django backend (`../apps/`) over the API. See
the [project architecture](../README.md#architecture) for how it fits.

> Note: the frontend is still changing; treat this README as a map, not a spec.

## Stack

- Vue 3 (`<script setup>`) + TypeScript
- Vite (dev server + build)
- vue-router (history mode)
- Pinia (`stores/`)
- Tailwind-style utility CSS (`style.css`)

Path alias `@/` resolves to `src/`.

## Scripts

```bash
npm run dev          # Vite dev server (port 5173, proxies to the API)
npm run build        # vue-tsc --noEmit && vite build
npm run type-check   # vue-tsc --noEmit
npm run format       # prettier --write src/
```

In normal use the app is served by Django at http://localhost:8000; the Vite
dev server is only for isolated frontend work with hot reload.

## Two modules, one flow

The app covers two analysis modules, **Seeds** and **Pollinators**, each with
the same seven-step flow. Routes are nested under the authenticated `AppShell`
layout (`router/index.ts`):

```
/<module>/upload                 configure + upload a camera-trap folder
/<module>/runs                   list runs
/<module>/runs/:id/detect        watch / control an inference run
/<module>/runs/:id/review        review and correct detections
/<module>/runs/:id/export        export CSV / crops / annotated images
/<module>/training               start a retraining job from reviewed data
/<module>/models                 model versions, activate a version
```

`/signin` and `/signup` are public (`meta.public`); everything else requires
auth. The default route redirects to `/seeds/upload`.

## Layout

```
src/
  api.ts            the fetch wrapper (auth + refresh; see below)
  main.ts           app bootstrap
  router/           routes + the auth guard
  stores/           Pinia stores: auth, theme
  pages/            one component per route (Pollinators*, Seeds*, Sign*, NotFound)
  components/        shared UI: AppShell, *Stepper, dialogs, ROIDrawer/ROIOverlay,
                     TrainingCharts, PageHeader, InfoPopover, forms, ThemeToggle
  lib/              config (API_BASE_URL), token (JWT manager), uploader,
                    model-tracks, confirm, utils
  mocks/            offline preview-mode fixtures (not used against the real API)
```

## API access and auth

All network calls go through `api(url, options)` in `src/api.ts`:

- prepends `API_BASE_URL` (`lib/config.ts`);
- attaches the JWT access token as a `Bearer` header (`lib/token.ts`);
- leaves `Content-Type` unset for `FormData` uploads;
- on a `401`, refreshes the token once (deduplicated across concurrent calls)
  via `/api/auth/refresh/` and retries; on failure it clears the tokens.

The router guard (`router/index.ts`) calls `auth.checkAuth()` and redirects
unauthenticated users to `/signin?next=...`. Auth tokens are JWT access +
refresh, issued by the backend `accounts` app.

The backend endpoints these pages call live under `/api/auth/`,
`/api/datasets/`, `/api/analysis/`, and `/api/pollinator/` (see
[apps/README.md](../apps/README.md)).

## Preview mode and mocks

`src/mocks/` holds static fixtures used by an offline preview mode so the design
can be exercised without a backend. The app runs against the **real API** by
default; the mocks are not a substitute for it and should not be edited as a way
to change app behaviour.
