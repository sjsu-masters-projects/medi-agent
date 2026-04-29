# Phase 6.7: Session Management & Auth Hardening

## Final Implementation

Phase 6.7 hardens authentication behavior for both the clinician and patient portals. The implementation is intentionally shared in shape across both apps while keeping role-specific refresh validation separate.

### Token Refresh

- Both portals mount a `useAuthSessionRefresh` hook from the Redux provider layer.
- The hook refreshes authenticated sessions when the access token is within the early refresh window.
- The hook also checks on browser focus so a user returning after sleep/backgrounding gets a fresh session before the next protected action.
- Refresh success updates local storage and Redux auth state silently.
- Refresh failure logs the user out locally and redirects to login with `reason=session_expired`.
- Refresh responses are role-checked by portal (`patient` vs `clinician`) before being accepted.

### Protected Route Redirects

- Protected routes redirect unauthenticated users to login with a sanitized `return_path`.
- Login pages preserve safe internal return paths and reject external/protocol-relative paths.
- Default post-login destinations remain role-specific:
  - Patient portal: `/today`
  - Clinician portal: `/dashboard`
- Invalid or expired sessions no longer strand users on stale protected UI.

### API 401 Handling

- Portal API clients detect authenticated `401` responses outside the login page.
- A stale authenticated session is cleared through the shared auth redirect helper.
- The user is returned to login with `reason=session_expired`.
- Login failures without an existing token remain on the login form so users can correct credentials.

### Logout Scope

- Existing logout flows clear local Redux/localStorage session state.
- Backend refresh-token invalidation is not implemented in this slice because Supabase refresh-token expiry is still the source of truth.
- If product/security later requires immediate refresh-token revocation, add a backend logout endpoint and wire both portal logout actions to it.

## Test Coverage

- Clinician portal:
  - login invalid-credential behavior
  - protected-route return path
  - safe return-path utilities
  - refresh hook success/no-op/focus/failure behavior
  - API client authenticated `401` redirect behavior
- Patient portal:
  - login return path and session-expired messaging
  - protected-route return path
  - refresh hook success/no-op/focus/failure behavior
  - API client authenticated `401` redirect behavior

## Production Notes

- Supabase auth redirect URLs are configured for:
  - `https://app.mediagent.live/*`
  - `https://clinician.mediagent.live/*`
  - local development callback URLs
- Custom portal domains are configured through Vercel/Cloudflare.
- Backend custom domain and email DNS setup are tracked separately from this code slice.
