# reporting/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('performance/doctors/', views.get_doctor_performance_report, name='doctor_performance'),

    # GET: /api/reporting/common-conditions/
    # Generates a report showing the most frequently recorded medical conditions among patients
    path('common-conditions/', views.get_common_conditons_report, name='get_common_conditons_report'),
]