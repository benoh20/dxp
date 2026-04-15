from django.urls import path

from . import views

urlpatterns = [
    # Chat interface
    path("",        views.chat_view,  name="chat"),
    path("query/",  views.query_view, name="query"),
]
