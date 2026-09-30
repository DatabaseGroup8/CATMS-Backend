from django.shortcuts import render
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

@csrf_exempt
def process_payment(request):
    # Step 1: Enforce POST method since we are writing data
    if request.method == 'POST':
        try:
            # Step 2: Parse the JSON payload
            data = json.loads(request.body)
            
            invoice_id = data.get('invoice_id')
            payment_amount = data.get('payment_amount')
            
            # Basic Validation: Ensure the frontend didn't send empty data
            if not invoice_id or payment_amount is None:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'invoice_id and payment_amount are required.'
                }, status=400)

            # Step 3: Open a secure database cursor
            with connection.cursor() as cursor:
                
                # Step 4: Execute the raw INSERT statement
                cursor.execute("""
                    INSERT INTO Payment (invoice_id, payment_amount) 
                    VALUES (%s, %s);
                """, [invoice_id, payment_amount])
                
                # Step 5: Retrieve the auto-generated Primary Key of the new payment
                cursor.execute("SELECT LAST_INSERT_ID();")
                payment_id = cursor.fetchone()[0]

            # Step 6: Return the success payload
            return JsonResponse({
                'status': 'success',
                'message': 'Payment processed successfully.',
                'payment_id': payment_id,
                'invoice_id': invoice_id,
                'amount_paid': payment_amount
            }, status=201)

        except Exception as e:
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
