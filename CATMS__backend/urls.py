"""
URL configuration for CATMS__backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Route API calls to their respective apps
    path('api/clinical/', include('clinical_core.urls')),
    path('api/registration/', include('registration.urls')),
    path('api/billing/', include('billing.urls')),
    path('api/reporting/', include('reporting.urls')),
    # GET request capturing the invoice ID directly from the URL
    path('balance/<int:invoice_id>/', views.get_outstanding_balance, name='get_outstanding_balance'),
    
    # POST requests that read their parameters from the JSON body
    path('payment/record/', views.record_payment, name='record_payment'),
    path('claim/process/', views.process_insurance_claim, name='process_insurance_claim'),
]
