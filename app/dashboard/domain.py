"""Dashboard page errors."""


class PageAuthenticationRequired(Exception):
    """Raised when an HTML page requires a login."""


class PageAccessDenied(Exception):
    """Raised when an HTML page is outside the current permission set."""
