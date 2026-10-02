# registration/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_patients, name='search_patients'),

    # GET: /api/registration/patient-appointments/?patient_id=5
    # Retrieves all appointments for a specific patient and returns the total appointment count
    path('patient-appointments/', views.get_patient_appointments, name= 'get_patient_appointments'),
]