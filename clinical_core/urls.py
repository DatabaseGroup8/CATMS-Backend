from django.urls import path
from . import views
from . import workflow_views as workflow
from . import catalogue_views

urlpatterns = [
    
    # POST: /api/clinical/patient-condition/add/
    path('patient-condition/add/', views.add_patient_condition, name='add_patient_condition'),
    
    # GET: /api/clinical/patient-history/5/
    path('patient-history/<int:patient_id>/', views.get_patient_history, name='get_patient_history'),

    # GET: /api/clinical/get-consultation-summary/?consultation_rec_id=5
    # Retrieves the details and duration of a specific consultation
    path('get-consultation-summary', views.get_consultation_summary, name = 'get_consultation_summary'),
    
    
    # POST: /api/clinical/conditions/category/add/
    path('conditions/category/add/', views.add_condition_category, name='add_condition_category'),
    
    # POST: /api/clinical/conditions/add/
    path('conditions/add/', views.add_condition, name='add_condition'),
    
    # POST: /api/clinical/treatments/category/add/
    path('treatments/category/add/', views.add_treatment_category, name='add_treatment_category'),
    
    # POST: /api/clinical/treatments/catalogue/add/
    

]


# Doctor schedule, completion and catalogues for the new workflow
urlpatterns += [
    path('doctors/me/appointments/', workflow.get_doctor_appointments, name='doctor_appointments'),
    path('appointments/<int:appointment_id>/complete/', workflow.mark_appointment_completed, name='mark_appointment_completed'),
    path('medications/add/', workflow.add_medication, name='add_medication'),
    path('medications/search/', workflow.search_medications, name='search_medications'),
    path('treatments/catalogue/add/', workflow.add_treatment_catalogue, name='add_treatment_catalogue'),
    path('treatments/search/', workflow.search_treatments, name='search_treatments'),

    path('conditions/categories/',catalogue_views.list_condition_categories,name='list_condition_categories'),
    path('conditions/',catalogue_views.list_conditions,name='list_conditions'),
    path('treatments/categories/',catalogue_views.list_treatment_categories,name='list_treatment_categories'),
    path('specializations/',catalogue_views.list_specializations,name='list_specializations'),
    path('doctors/<int:doctor_id>/specializations/',catalogue_views.assign_doctor_specialization,name='assign_doctor_specialization'),

    # POST: /api/clinical/specializations/add/
    path(
    'specializations/add/',
    catalogue_views.create_specialization,
    name='create_specialization'
        ),
]
