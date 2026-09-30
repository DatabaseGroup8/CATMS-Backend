from django.urls import path
from . import views

urlpatterns = [
    
    # POST: /api/clinical/patient-condition/add/
    path('patient-condition/add/', views.add_patient_condition, name='add_patient_condition'),
    
    # GET: /api/clinical/patient-history/5/
    path('patient-history/<int:patient_id>/', views.get_patient_history, name='get_patient_history'),
]