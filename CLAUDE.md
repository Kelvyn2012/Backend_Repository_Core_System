# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (activate venv first)
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Generate migrations after model changes
python manage.py makemigrations

# Seed the database (idempotent; --clear to wipe and reseed)
python manage.py seed_profiles
python manage.py seed_profiles --clear

# Start dev server
python manage.py runserver

# Run all 118 tests
python manage.py test api users

# Run a specific test class
python manage.py test api.tests.NLParserTests
python manage.py test api.tests.ProfileListTests
python manage.py test api.tests.ProfileSearchTests
python manage.py test users.tests.TokenLifecycleTests
python manage.py test users.tests.RoleEnforcementTests
python manage.py test users.tests.APIVersionMiddlewareTests
```

## Environment variables

Create `.env` in the project root:

```dotenv
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=*
DATABASE_URL=postgresql://user:password@host:5432/dbname
GITHUB_CLIENT_ID=your_github_app_client_id
GITHUB_CLIENT_SECRET=your_github_app_client_secret
GITHUB_CALLBACK_URL=http://localhost:8000/auth/github/callback/
# Optional — Redis for distributed rate limiting
CACHE_URL=redis://localhost:6379/1
```

Without `DATABASE_URL`, the app falls back to individual vars: `POSTGRES_DB`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

## Architecture

Two Django apps:

- **`users/`** — authentication, tokens, RBAC
- **`api/`** — profile data, filtering, NL search

### Request flow

```
Every /api/* request:
  RequestLoggingMiddleware → APIVersionMiddleware (X-API-Version: 1 required)
  → BearerTokenAuthentication → IsActiveUser / IsAdminRole permission
  → view handler

/auth/* endpoints:
  authentication_classes = []  (no auth required)
  permission_classes = []
  throttle_classes = [AuthThrottle]  (10 req/min per IP)
```

### URL routing

```
/auth/github/              → GitHubAuthorizeView   (GET)
/auth/github/callback/     → GitHubCallbackView    (GET)
/auth/refresh/             → RefreshTokenView      (POST)
/auth/logout/              → LogoutView            (POST)

/api/profiles/export/      → ProfileExportView     (GET, analyst+)
/api/profiles/search/      → ProfileSearchView     (GET, analyst+)
/api/profiles/             → ProfileView           (GET analyst+, POST admin)
/api/profiles/<uuid:id>/   → ProfileDetailView     (GET analyst+, DELETE admin)
```

URL order in `api/urls.py` matters — `export/` and `search/` must be before `<uuid:id>/`.

### Key modules

- **[users/models.py](users/models.py)** — `User`, `OAuthState`, `AccessToken`, `RefreshToken`. Token TTLs defined at module level: access=3min, refresh=5min, state=10min.

- **[users/services.py](users/services.py)** — `PKCEService` (code_verifier/challenge generation), `GitHubOAuthService` (concurrent token exchange + user fetch), `TokenService` (issue_token_pair, refresh, revoke), `create_or_update_user`.

- **[users/authentication.py](users/authentication.py)** — `BearerTokenAuthentication`: reads `Authorization: Bearer <token>`, validates against `AccessToken` table, returns `(user, token)`.

- **[users/permissions.py](users/permissions.py)** — `IsActiveUser` (base, any authenticated active user), `IsAdminRole` (role=admin), `IsAnalystOrAdmin` (role in admin/analyst). All extend each other; never scatter role checks into view logic.

- **[users/middleware.py](users/middleware.py)** — `APIVersionMiddleware` checks `HTTP_X_API_VERSION` on all non-`/auth/` and non-`/admin/` requests. `RequestLoggingMiddleware` logs method/path/status/ms for every request.

- **[users/throttling.py](users/throttling.py)** — `AuthThrottle` (10/min per IP), `UserThrottle` (60/min per authenticated user). Applied via `throttle_classes` on view classes.

- **[api/filters.py](api/filters.py)** — `build_profile_queryset(queryset, params)` validates and applies all query params. Returns `(queryset, None)` or `(None, error_dict)`. The `error_dict` carries `_status_code` for the caller.

- **[api/parser.py](api/parser.py)** — Pure regex + lookup NL parser. `parse_query(q)` returns a filter-params dict or `None`. `"young"` → min_age=16, max_age=24. Both genders together → no gender filter.

- **[api/services.py](api/services.py)** — `ProfileAggregatorService.fetch_and_process_data(name)` fires three external API calls concurrently. Raises `ExternalAPIException` or `InvalidProfileDataException` on failure → caller maps to 502.

- **[api/pagination.py](api/pagination.py)** — Extended `ProfilePagination` adds `total_pages` and `links` (self/next/prev) to the response envelope.

### Critical settings note

`URL_FORMAT_OVERRIDE = None` is set in `REST_FRAMEWORK` to prevent DRF 3.17's content negotiator from intercepting `?format=csv` on the export endpoint. Without this, DRF raises `Http404` because no `csv` renderer is registered.

### Token rotation contract

`RefreshToken` is single-use. On `POST /auth/refresh/`:
1. Validate token is not revoked and not expired
2. Set `is_revoked=True` on the old token
3. Issue new access + refresh pair

Any attempt to reuse a refresh token returns 401.

### POST /api/profiles/ idempotency

`name` is normalized to `strip().lower()`. Pre-check via `Profile.objects.get(name=normalized)` returns 200 if found. `IntegrityError` on `create()` is caught as a race-condition fallback and also returns 200.

### Test patterns

All HTTP tests that hit `/api/*` need both credentials in `APIClient`:
```python
client.credentials(
    HTTP_AUTHORIZATION=f"Bearer {token.token}",
    HTTP_X_API_VERSION="1",
)
```

Auth endpoint tests that use `AuthThrottle` must call `cache.clear()` in `setUp()` to prevent throttle accumulation across tests.
