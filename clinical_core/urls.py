from django.urls import path
from . import views

urlpatterns = [
    path('patient-condition/add/', views.add_patient_condition, name='add_patient_condition'),
]