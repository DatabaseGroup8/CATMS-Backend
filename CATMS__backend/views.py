import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

#View 1:Get Outstanding Balance
@csrf_exempt
def get_outstanding_balance(request, invoice_id):
    #Step 2:Check the Request Method
    if request.method == 'GET':
        try:
            #Step 4:Secure database execution block
            with connection.cursor() as cursor:
                #Call the custom database function to calculate the outstanding balance
                cursor.execute("SELECT CalculateOutstandingBalance(%s);", [invoice_id])
                row = cursor.fetchone()
                
                if row and row[0] is not None:
                    #Step 5: Return JSON Response
                    return JsonResponse({
                        'status': 'success', 
                        'data': {'outstanding_balance': float(row[0])}
                    }, status=200)
                else:
                    return JsonResponse({'status': 'error', 'message': 'Invoice not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)


