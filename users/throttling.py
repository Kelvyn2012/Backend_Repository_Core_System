from rest_framework.throttling import SimpleRateThrottle


class AuthThrottle(SimpleRateThrottle):
    """10 req/min per IP — applied to all /auth/* endpoints."""

    scope = "auth"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class UserThrottle(SimpleRateThrottle):
    """60 req/min per authenticated user (falls back to IP for anon)."""

    scope = "user"

    def get_cache_key(self, request, view):
        if request.user and getattr(request.user, "is_authenticated", False):
            ident = str(request.user.id)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
