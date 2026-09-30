# billing/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('payment/process/', views.process_payment, name='process_payment'),
]