import { getBootstrap } from '@/api/client';
import { normalizeBootstrap } from '@/lib/bootstrapAdapter';

let cachedBootstrap = null;
let inFlightBootstrap = null;

const WAKE_TIMEOUT_MS = 90000;
const WAKE_RETRY_DELAYS_MS = [0, 3000, 7000, 12000];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function describeError(error) {
  if (!error) return 'Unknown error';
  if (error.status) return `HTTP ${error.status}`;
  return error.message || String(error);
}

export async function loadBootstrap({
  force = false,
  wakeRetry = false,
  timeoutMs = wakeRetry ? WAKE_TIMEOUT_MS : undefined,
  onWakeStatus = null,
} = {}) {
  if (!force && cachedBootstrap) return cachedBootstrap;
  if (!force && inFlightBootstrap) return inFlightBootstrap;

  const delays = wakeRetry ? WAKE_RETRY_DELAYS_MS : [0];

  inFlightBootstrap = (async () => {
    let lastError = null;
    for (let index = 0; index < delays.length; index += 1) {
      const attempt = index + 1;
      if (delays[index] > 0) await sleep(delays[index]);

      onWakeStatus?.({
        endpoint: '/api/bootstrap',
        attempt,
        maxAttempts: delays.length,
        timeoutMs,
        apiBase: null,
        lastError: lastError ? describeError(lastError) : null,
        status: 'retrying',
      });

      try {
        const payload = await getBootstrap({ timeoutMs });
        cachedBootstrap = normalizeBootstrap(payload);
        onWakeStatus?.({
          endpoint: '/api/bootstrap',
          attempt,
          maxAttempts: delays.length,
          timeoutMs,
          lastError: null,
          status: 'ok',
        });
        return cachedBootstrap;
      } catch (error) {
        lastError = error;
        onWakeStatus?.({
          endpoint: '/api/bootstrap',
          attempt,
          maxAttempts: delays.length,
          timeoutMs,
          lastError: describeError(error),
          httpStatus: error?.status || null,
          status: 'error',
        });
      }
    }

    throw lastError;
  })().finally(() => {
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
