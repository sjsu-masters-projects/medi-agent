"""Auth — signup, login, tokens."""


class AuthService:

    async def signup_patient(self, email: str) -> dict:
        """Send magic link to patient."""
        # TODO: Supabase magic link
        raise NotImplementedError

    async def login_clinician(self, email: str, password: str) -> dict:
        """Authenticate with email/password."""
        # TODO: Supabase email/password auth
        raise NotImplementedError

    async def refresh_token(self, refresh_token: str) -> dict:
        # TODO: token refresh
        raise NotImplementedError
