from django.urls import path 
from . import views 
urlpatterns = [  
               path('appointments/branch-daily/',         
                    views.branch_daily_appointments, name='branch_daily_appointments'),    
               path('revenue/doctors/',         
                    views.doctor_revenue, name='doctor_revenue'),  
               path('outstanding/patients/',         
                    views.patients_with_outstanding_balances,         
                    name='patients_with_outstanding_balances'),    
               path('treatments/categories/',         
                    views.treatments_by_category, name='treatments_by_category'),    
               path('insurance-vs-out-of-pocket/',         
                    views.insurance_vs_out_of_pocket,         
                    name='insurance_vs_out_of_pocket'),    
               path('medication-usage/',         
                    views.medication_usage_branch_scoped,         
                    name='medication_usage'),
]