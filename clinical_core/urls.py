from django.urls import path
from . import views

urlpatterns = [
    
    # POST: /api/clinical/patient-condition/add/
    path('patient-condition/add/', views.add_patient_condition, name='add_patient_condition'),
    
    # GET: /api/clinical/patient-history/5/
    path('patient-history/<int:patient_id>/', views.get_patient_history, name='get_patient_history'),

    # GET: /api/clinical/get-consultation-summary/?consultation_rec_id=5
    # Retrieves the details and duration of a specific consultation
    path('get-consultation-summary', views.get_consultation_summary, name = 'get_consultation_summary'),
    
    path('medications/add/', views.add_medication, name='add_medication'),
    
    # POST: /api/clinical/conditions/category/add/
    path('conditions/category/add/', views.add_condition_category, name='add_condition_category'),
    
    # POST: /api/clinical/conditions/add/
    path('conditions/add/', views.add_condition, name='add_condition'),
    
    # POST: /api/clinical/treatments/category/add/
    path('treatments/category/add/', views.add_treatment_category, name='add_treatment_category'),
    
    # POST: /api/clinical/treatments/catalogue/add/
    path('treatments/catalogue/add/', views.add_treatment_catalogue, name='add_treatment_catalogue'),
    
    path('consultations/create/', views.create_consultation, name='create_consultation'),

]