/**
 * PumpIQ MCP Server — HTTP Client with Retry & Error Parsing
 *
 * Wraps native fetch with:
 *   - Exponential backoff retry (3 attempts)
 *   - NOAA "200 with error in body" detection
 *   - Timeout enforcement (30s default)
 *   - Structured error messages for AI consumption
 */

export interface FetchOptions {
  headers?: Record<string, string>;
  timeoutMs?: number;
  maxRetries?: number;
  /** Name for error messages (e.g. "NOAA CO-OPS") */
  sourceName?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly source: string,
    public readonly statusCode?: number,
    public readonly remedy?: string
  ) {
    super(message);
    this.name = "ApiError";
  }

  toToolResult(): string {
    let msg = `ERROR [${this.source}]: ${this.message}`;
    if (this.statusCode) msg += ` (HTTP ${this.statusCode})`;
    if (this.remedy) msg += `\n\nSuggested fix: ${this.remedy}`;
    return msg;
  }
}

export async function fetchJson<T>(
  url: string,
  opts: FetchOptions = {}
): Promise<T> {
  const {
    headers = {},
    timeoutMs = 30_000,
    maxRetries = 3,
    sourceName = "External API",
  } = opts;

  let lastError: Error | null = null;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      const response = await fetch(url, {
        headers: { Accept: "application/json", ...headers },
        signal: controller.signal,
      });

      clearTimeout(timer);

      if (!response.ok) {
        throw new ApiError(
          `HTTP ${response.status} ${response.statusText}`,
          sourceName,
          response.status,
          response.status === 429
            ? "Rate limit hit. Wait a moment and retry."
            : response.status === 404
              ? "Resource not found. Check station ID or parameter."
              : undefined
        );
      }

      const data = (await response.json()) as T;

      // NOAA CO-OPS returns 200 but puts errors in the body
      if (data && typeof data === "object" && "error" in data) {
        const errObj = data as Record<string, unknown>;
        const errMsg =
          typeof errObj.error === "object" && errObj.error !== null
            ? (errObj.error as { message?: string }).message
            : String(errObj.error);
        throw new ApiError(
          errMsg ?? "Unknown API error in response body",
          sourceName,
          200,
          "The API returned 200 OK but the response body contains an error. Check parameters."
        );
      }

      return data;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      if (err instanceof ApiError && err.statusCode && err.statusCode < 500) {
        throw err; // Don't retry client errors
      }

      if (attempt < maxRetries - 1) {
        const delay = Math.pow(2, attempt) * 500;
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }

  throw (
    lastError ??
    new ApiError("Request failed after retries", sourceName)
  );
}
