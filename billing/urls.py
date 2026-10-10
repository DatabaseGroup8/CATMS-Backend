"""REPLACE existing billing/urls.py with this complete file."""
from django.urls import path
from . import workflow_views as views
from . import insurance_admin_views as admin_views

urlpatterns = [
    path('insurance/packages/', admin_views.create_insurance_package, name='create_insurance_package'),
    path('insurance/patients/assign/', admin_views.assign_patient_insurance, name='assign_patient_insurance'),
    path('completed-appointments/', views.get_completed_appointments,
         name='completed_appointments'),
    path('consultations/finalize/', views.finalize_consultation_bill,
         name='finalize_consultation_bill'),
    path('invoices/<int:invoice_id>/summary/', views.get_invoice_summary,
         name='invoice_summary'),
    path('invoices/<int:invoice_id>/insurances/', views.get_patient_insurance_for_invoice,
         name='invoice_insurance_options'),
    path('invoices/<int:invoice_id>/insurance/', views.apply_invoice_insurance,
         name='apply_invoice_insurance'),
    path('payment/process/', views.process_full_checkout,
         name='process_full_checkout'),
    path('invoices/<int:invoice_id>/insurance/resolve/', views.resolve_insurance_claim,
         name='resolve_insurance_claim'),
    path('invoices/<int:invoice_id>/insurance/settlement/', views.record_insurance_settlement,
         name='record_insurance_settlement'),
    # Optionally preserve the old balance-only route, using the safe summary view:
    path('balance/<int:invoice_id>/', views.get_outstanding_balance_compat,
         name='outstanding_balance'),
]
