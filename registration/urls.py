# registration/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_patients, name='search_patients'),
]