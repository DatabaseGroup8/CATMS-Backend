from django.urls import path
from . import views
from . import directory_views

urlpatterns = [
    
    path('api/auth/login/', views.login_view, name='login_view'),
    path('api/auth/register/staff/', views.register_staff, name='register_staff'),
    path('api/auth/register/doctor/', views.register_doctor, name='register_doctor'),
    path('api/auth/branches/', directory_views.list_branches, name='list_branches'),
    path('api/auth/staff/', directory_views.list_staff, name='list_staff'),
]