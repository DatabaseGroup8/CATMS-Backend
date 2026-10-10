"""Complete reporting URL configuration: required + supplementary reports."""
from django.urls import path
from . import views
from . import required_reports

urlpatterns = [
    # Five reports required by the CATMS project brief:
    path('appointments/branch-daily/', required_reports.branch_daily_appointments,
         name='branch_daily_appointments'),
    path('revenue/doctors/', required_reports.doctor_revenue,
         name='doctor_revenue'),
    path('outstanding/patients/', required_reports.patients_with_outstanding_balances,
         name='patients_with_outstanding_balances'),
    path('treatments/categories/', required_reports.treatments_by_category,
         name='treatments_by_category'),
    path('insurance-vs-out-of-pocket/', required_reports.insurance_vs_out_of_pocket,
         name='insurance_vs_out_of_pocket'),

    # Existing supplementary reports: keep their URLs working.
    path('performance/doctors/', views.get_doctor_performance_report,
         name='doctor_performance'),
    path('common-conditions/', views.get_common_conditons_report,
         name='get_common_conditons_report'),
    path('medication-usage/', required_reports.medication_usage_branch_scoped,
         name='get_medication_usage_report'),
]
