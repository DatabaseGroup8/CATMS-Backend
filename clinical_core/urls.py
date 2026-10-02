from django.urls import path
from . import views

urlpatterns = [
    
    # POST: /api/clinical/patient-condition/add/
    path('patient-condition/add/', views.add_patient_condition, name='add_patient_condition'),
    
    # GET: /api/clinical/patient-history/5/
    path('patient-history/<int:patient_id>/', views.get_patient_history, name='get_patient_history'),

    # POST: /api/clinical/add-treatment/
    # Adds a treatment/service to a medical record
    path('add-treatment/', views.add_treatment, name='add_treatment'),

    # GET: /api/clinical/get-consultation-summary/?consultation_rec_id=5
    # Retrieves the details and duration of a specific consultation
    path('get-consultation-summary', views.get_consultation_summary, name = 'get_consultation_summary'),

]