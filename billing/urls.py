
from django.urls import path
from . import views

urlpatterns = [
    path(
        'payment/process/',
        views.process_full_checkout,
        name='process_full_checkout'
    ),

    path(
        'balance/<int:invoice_id>/',
        views.outstanding_balance,
        name='outstanding_balance'
    ),
]
