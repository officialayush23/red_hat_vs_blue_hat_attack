// Deterministic PRNG so demo data is stable across renders/reloads
// instead of re-randomizing on every mount.
export function mulberry32(seed) {
  let a = seed;
  return function rand() {
    a |= 0;
    a = a + 0x6d2b79f5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
export function seededInt(rand, min, max) {
  return Math.floor(rand() * (max - min + 1)) + min;
}
export function pick(rand, arr) {
  return arr[Math.floor(rand() * arr.length)];
}
export function daysAgoIso(days, hours = 0) {
  const d = new Date("2026-08-29T09:00:00Z");
  d.setDate(d.getDate() - days);
  d.setHours(d.getHours() - hours);
  return d.toISOString();
}
