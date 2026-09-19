/**
 * Carrying the access token to a WebSocket without putting it in the URL.
 *
 * A browser cannot set an `Authorization` header when opening a WebSocket, which is why
 * the token used to be a query parameter. That published it: the backend writes the full
 * request path to its access log, so every connection wrote a usable session token where
 * anyone with log access could read it, and query strings also reach proxies, browser
 * history and `Referer` headers.
 *
 * `Sec-WebSocket-Protocol` is the standard way around the missing header. The browser
 * sends these values as a header, and the server reads the token from the second entry
 * and echoes back only the scheme name.
 */

/** The scheme name, matching `WS_AUTH_SUBPROTOCOL` on the backend. */
export const WS_AUTH_SCHEME = "bearer";

/**
 * Build the subprotocol list for an authenticated socket.
 *
 * Pass the result as the second argument to `new WebSocket(url, protocols)`. The token
 * must never also be appended to the URL.
 */
export function socketAuthProtocols(token: string): string[] {
    return [WS_AUTH_SCHEME, token];
}
