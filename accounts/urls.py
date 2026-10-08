from django.urls import path
from . import views

urlpatterns = [
    
    path('api/auth/login/', views.login_view, name='login_view'),
    path('api/auth/register/staff/', views.register_staff, name='register_staff'),
    path('api/auth/register/doctor/', views.register_doctor, name='register_doctor'),
]