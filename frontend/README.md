# FraudShield — Frontend Prototype

An agentic AI system that continuously attacks, learns from, and hardens fraud defenses. This is the
frontend dashboard: a full React/TypeScript prototype of the FraudShield product experience, running
entirely on realistic mock data so the UI, flows, and visualizations can be reviewed and demoed before
the backend exists.

## Tech stack

- React 19 + TypeScript
- Vite
- Tailwind CSS v4
- shadcn/ui (`radix-rhea` style) — every UI primitive (cards, tables, badges, charts, dialogs, etc.)
  comes from this one component library, no other UI/chart libraries are used
- TanStack React Query — data fetching/caching against the mock service layer
- React Router — client-side routing
- Framer Motion — used sparingly, for the live agent activity reveal animation
- Recharts, via shadcn's `chart.tsx` wrapper — all charts

## Running it

```bash
npm install
npm run dev
```

Then open the printed local URL (typically `http://localhost:5173`).

Other scripts:

```bash
npm run build     # production build (outputs to dist/)
npm run preview   # serve the production build locally
npm run lint      # eslint
```

## How the data layer works — and how to wire up the real backend later

There is **no backend yet**. Every page reads through TanStack Query hooks
(`src/hooks/*`) that call a mock service layer (`src/services/api/*`). Each function in that
service layer is documented with the exact REST endpoint it stands in for, e.g.:

```ts
// src/services/api/runs.ts

// GET /api/runs
export async function listRuns(): Promise<DefenseRun[]> { ... }

// GET /api/runs/:id
export async function getRun(id: string): Promise<DefenseRun | undefined> { ... }
```

The mock functions return data generated deterministically (seeded random) from
`src/data/mockStore.ts` and `src/data/attackCatalog.ts`, wrapped in a small artificial delay
(`mockDelay`) to simulate network latency.

**To rewire this to a real FastAPI backend**, replace the body of each function in
`src/services/api/*.ts` with an actual `fetch`/HTTP call to the matching endpoint, keeping the same
function signature and return type. Because the hooks, components, and pages only ever import from
`src/hooks/*` (never touch `src/data/*` directly), no UI code needs to change — only the four files
in `src/services/api/`.

## Project structure

```
src/
  types/            Domain types shared by the mock layer and the future API (AttackFamily, DefenseRun, ...)
  data/              Seeded mock data generators (attack catalog, runs, evaluation cases, weaknesses, ...)
  services/api/      Mock service layer — one file per resource, documents the REST shape it mimics
  hooks/             TanStack Query hooks wrapping the service layer
  components/
    ui/              shadcn/ui primitives (generated, not hand-edited beyond icon wiring)
    layout/          Sidebar, Topbar, AppShell
    shared/          PageHeader, StatCard, badges, AgentStepList — reused across features
  features/          One folder per page/domain (dashboard, defense-runs, agents, attacks,
                     evaluation, weaknesses, results, performance, reports, architecture)
  routes/            React Router route table
```

## Pages

| Route | Page |
|---|---|
| `/` | Overview dashboard |
| `/runs` | Defense runs list |
| `/runs/new` | Create a new defense run |
| `/runs/:runId/activity` | Live agent activity (Red Team orchestration) |
| `/attacks` | Attack library |
| `/attacks/:attackId` | Attack detail |
| `/runs/:runId/evaluation` | Blue Team evaluation pipeline |
| `/runs/:runId/weaknesses` | Weakness analysis |
| `/runs/:runId/mutation` | Adaptive mutation |
| `/runs/:runId/results` | Run results |
| `/performance` | Model / defense performance |
| `/runs/:runId/report` | Reports / export |
| `/architecture` | System architecture |

## Note on the data shown

All numbers, scores, and timelines are seeded demo data generated on load — none of it reflects a
real fraud dataset or a live model. This is called out in the top bar ("Prototype · Demo Data") and in
the sidebar footer throughout the app.
