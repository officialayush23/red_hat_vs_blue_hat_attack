// Thin mock "HTTP client" shim. Every function in services/api/* is written
// as an async function with this exact signature shape a real fetch() call
// would have, so swapping the mock implementation for
//   fetch(`${API_BASE}/runs`).then(r => r.json())
// later is a body-only change — call sites and React Query hooks stay put.

const SIMULATED_LATENCY_MS = 220;
export function mockDelay(value, ms = SIMULATED_LATENCY_MS) {
  return new Promise(resolve => setTimeout(() => resolve(value), ms));
}
