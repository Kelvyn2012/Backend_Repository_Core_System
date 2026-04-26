from django.urls import path

from .views import ProfileDetailView, ProfileExportView, ProfileSearchView, ProfileView

urlpatterns = [
    path("profiles/export/", ProfileExportView.as_view(), name="profiles-export"),
    path("profiles/search/", ProfileSearchView.as_view(), name="profiles-search"),
    path("profiles/", ProfileView.as_view(), name="profiles"),
    path("profiles/<uuid:id>/", ProfileDetailView.as_view(), name="profile-detail"),
]
