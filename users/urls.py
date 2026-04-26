from django.urls import path

from .views import GitHubAuthorizeView, GitHubCallbackView, LogoutView, RefreshTokenView

urlpatterns = [
    path("github/", GitHubAuthorizeView.as_view(), name="github-authorize"),
    path("github/callback/", GitHubCallbackView.as_view(), name="github-callback"),
    path("refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
