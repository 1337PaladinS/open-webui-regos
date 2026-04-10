/**
 * PumpIQ MCP Server — Token Bucket Rate Limiter
 *
 * Enforces client-side rate limits to avoid being throttled by external APIs.
 * NOAA CDO: 5 requests/sec, 10,000 requests/day
 * Other APIs: No documented limits, but we use sensible defaults.
 */

interface BucketConfig {
  maxTokens: number;     // Max burst capacity
  refillRate: number;    // Tokens added per second
  dailyLimit?: number;   // Optional daily cap
}

interface Bucket {
  tokens: number;
  lastRefill: number;    // epoch ms
  dailyCount: number;
  dailyResetAt: number;  // epoch ms
  config: BucketConfig;
}

const buckets = new Map<string, Bucket>();

const PRESETS: Record<string, BucketConfig> = {
  "noaa-cdo": { maxTokens: 5, refillRate: 5, dailyLimit: 10000 },
  "noaa-coops": { maxTokens: 10, refillRate: 10 },
  "usgs": { maxTokens: 10, refillRate: 10 },
  "sfwmd": { maxTokens: 5, refillRate: 3 },
};

function getBucket(name: string): Bucket {
  if (!buckets.has(name)) {
    const config = PRESETS[name] ?? { maxTokens: 10, refillRate: 5 };
    const now = Date.now();
    buckets.set(name, {
      tokens: config.maxTokens,
      lastRefill: now,
      dailyCount: 0,
      dailyResetAt: now + 86_400_000,
      config,
    });
  }
  return buckets.get(name)!;
}

function refill(bucket: Bucket): void {
  const now = Date.now();
  const elapsed = (now - bucket.lastRefill) / 1000;
  bucket.tokens = Math.min(
    bucket.config.maxTokens,
    bucket.tokens + elapsed * bucket.config.refillRate
  );
  bucket.lastRefill = now;

  // Reset daily counter if past midnight
  if (now >= bucket.dailyResetAt) {
    bucket.dailyCount = 0;
    bucket.dailyResetAt = now + 86_400_000;
  }
}

/**
 * Acquire a token from the named rate limiter bucket.
 * Returns immediately if a token is available.
 * Waits (up to ~1s) if the bucket is empty.
 * Throws if daily limit is exceeded.
 */
export async function acquireToken(bucketName: string): Promise<void> {
  const bucket = getBucket(bucketName);
  refill(bucket);

  // Check daily limit
  if (
    bucket.config.dailyLimit &&
    bucket.dailyCount >= bucket.config.dailyLimit
  ) {
    throw new Error(
      `Rate limit exceeded: ${bucketName} daily limit of ${bucket.config.dailyLimit} requests reached. Resets at midnight UTC.`
    );
  }

  // Wait if no tokens available
  if (bucket.tokens < 1) {
    const waitMs = ((1 - bucket.tokens) / bucket.config.refillRate) * 1000;
    await new Promise((resolve) => setTimeout(resolve, Math.min(waitMs, 1000)));
    refill(bucket);
  }

  bucket.tokens -= 1;
  bucket.dailyCount += 1;
}
