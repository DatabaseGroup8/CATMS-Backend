# reporting/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('performance/doctors/', views.get_doctor_performance_report, name='doctor_performance'),
]