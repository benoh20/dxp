from django.conf import settings
from django.contrib import admin
from django.urls import include, path

# Admin is mounted at the path configured in settings.ADMIN_URL_PATH
# (default: admin/). Override per-environment via the ADMIN_URL_PATH env var
# so a public deployment doesn't expose /admin/ at the obvious URL.
urlpatterns = [
    path(settings.ADMIN_URL_PATH, admin.site.urls),
    # Django built-in i18n routes: /i18n/setlang/ accepts a POST with
    # `language` and `next` and stores the choice in a cookie + session.
    # Wired in Milestone Q so the language switcher in the sidebar works.
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("chat.urls")),
]
