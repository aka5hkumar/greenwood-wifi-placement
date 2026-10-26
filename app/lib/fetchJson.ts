/**
 * Fetch JSON without assuming the response is JSON.
 *
 * A serverless function that times out or crashes returns an HTML error page,
 * and calling res.json() on that throws "JSON.parse: unexpected character at
 * line 1 column 1" — which surfaced to users instead of a usable message.
 * This reads the body as text first and only parses when it actually looks
 * like JSON, so transport-level failures get a sentence a human can act on.
 */
export async function fetchJson<T>(
  input: RequestInfo,
  init?: RequestInit
): Promise<{ ok: true; data: T } | { ok: false; message: string; status: number }> {
  let res: Response;
  try {
    res = await fetch(input, init);
  } catch (e) {
    return {
      ok: false,
      status: 0,
      message:
        e instanceof Error && e.name === "AbortError"
          ? "The request took too long and was cancelled."
          : "Could not reach the server. Check your connection and try again.",
    };
  }

  const body = await res.text();
  const looksJson = body.trimStart().startsWith("{") || body.trimStart().startsWith("[");

  if (!looksJson) {
    // Almost always an upstream timeout/5xx HTML page.
    const message =
      res.status === 504 || res.status === 408
        ? "The server took too long to respond. Large or data-dense sites can exceed the time limit — try a smaller area."
        : `The server returned an unexpected response (HTTP ${res.status}).`;
    return { ok: false, status: res.status, message };
  }

  try {
    return { ok: true, data: JSON.parse(body) as T };
  } catch {
    return {
      ok: false,
      status: res.status,
      message: "The server returned a malformed response.",
    };
  }
}
