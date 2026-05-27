import { getBootstrap } from '@/api/client';
import { normalizeBootstrap } from '@/lib/bootstrapAdapter';

let cachedBootstrap = null;
let inFlightBootstrap = null;

export async function loadBootstrap({ force = false } = {}) {
  if (!force && cachedBootstrap) return cachedBootstrap;
  if (!force && inFlightBootstrap) return inFlightBootstrap;

  inFlightBootstrap = getBootstrap()
    .then((payload) => {
      cachedBootstrap = normalizeBootstrap(payload);
      return cachedBootstrap;
    })
    .finally(() => {
      inFlightBootstrap = null;
    });

  return inFlightBootstrap;
}

export function getCachedBootstrap() {
  return cachedBootstrap;
}

export function clearBootstrapCache() {
  cachedBootstrap = null;
  inFlightBootstrap = null;
}
