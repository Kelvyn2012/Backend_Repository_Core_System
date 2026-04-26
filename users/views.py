from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OAuthState
from .services import GitHubOAuthService, PKCEService, TokenService, create_or_update_user
from .throttling import AuthThrottle


def _error(message: str, http_status: int) -> Response:
    return Response({"status": "error", "message": message}, status=http_status)


def _github_service() -> GitHubOAuthService:
    return GitHubOAuthService(
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        callback_url=settings.GITHUB_CALLBACK_URL,
    )


class GitHubAuthorizeView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AuthThrottle]

    def get(self, request):
        state = PKCEService.generate_state()
        verifier = PKCEService.generate_verifier()
        challenge = PKCEService.generate_challenge(verifier)

        OAuthState.create(state, verifier)

        redirect_url = _github_service().get_authorization_url(state, challenge)

        return Response(
            {
                "status": "success",
                "redirect_url": redirect_url,
                "state": state,
                "code_challenge": challenge,
            }
        )


class GitHubCallbackView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AuthThrottle]

    def get(self, request):
        error = request.query_params.get("error")
        if error:
            desc = request.query_params.get("error_description", error)
            return _error(f"GitHub denied authorization: {desc}", status.HTTP_400_BAD_REQUEST)

        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if not code or not state:
            return _error("Missing code or state parameter", status.HTTP_400_BAD_REQUEST)

        try:
            oauth_state = OAuthState.objects.get(state=state)
        except OAuthState.DoesNotExist:
            return _error("Invalid or unknown state", status.HTTP_400_BAD_REQUEST)

        if not oauth_state.is_valid():
            oauth_state.delete()
            return _error("OAuth state expired, please restart login", status.HTTP_400_BAD_REQUEST)

        verifier = oauth_state.code_verifier
        oauth_state.delete()  # single-use

        try:
            gh_token = _github_service().exchange_code(code, verifier)
            gh_user = _github_service().get_user_data(gh_token)
        except Exception as exc:
            return _error(str(exc), status.HTTP_502_BAD_GATEWAY)

        user = create_or_update_user(gh_user)

        if not user.is_active:
            return _error("Account is deactivated", status.HTTP_403_FORBIDDEN)

        access, refresh = TokenService.issue_token_pair(user)

        return Response(
            {
                "status": "success",
                "access_token": access.token,
                "refresh_token": refresh.token,
                "token_type": "Bearer",
                "expires_in": 180,
            },
            status=status.HTTP_200_OK,
        )


class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AuthThrottle]

    def post(self, request):
        rt_str = request.data.get("refresh_token")
        if not rt_str:
            return _error("Missing refresh_token", status.HTTP_400_BAD_REQUEST)

        access, refresh, err = TokenService.refresh(rt_str)
        if err:
            return _error(err, status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "status": "success",
                "access_token": access.token,
                "refresh_token": refresh.token,
            }
        )


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AuthThrottle]

    def post(self, request):
        rt_str = request.data.get("refresh_token")
        if rt_str:
            TokenService.revoke(rt_str)
        return Response({"status": "success", "message": "Logged out successfully"})
