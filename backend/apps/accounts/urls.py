from django.urls import path
from .views import SessionView, SignOutView, DevLoginView, SignInView

urlpatterns = [
    path("session", SessionView.as_view(), name="session"),
    path("session/sign-in", SignInView.as_view(), name="session-sign-in"),
    path("session/sign-out", SignOutView.as_view(), name="session-sign-out"),
    path("auth/dev-login", DevLoginView.as_view(), name="dev-login"),
]
