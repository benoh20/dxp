from django.contrib import admin
from django.urls import include, path

from chat import views as auth_views

urlpatterns = [
    path("admin/",          admin.site.urls),

    # Auth routes — always unauthenticated-accessible
    path("auth/login/",     auth_views.login_view,    name="login"),
    path("auth/register/",  auth_views.register_view, name="register"),
    path("auth/logout/",    auth_views.logout_view,   name="logout"),

    # Chat application
    path("chat/",           include("chat.urls")),
]
