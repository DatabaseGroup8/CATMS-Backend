from django.shortcuts import render
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.db import DatabaseError, connection
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

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

@require_GET
def outstanding_balance(request, invoice_id=None):
    """GET an invoice balance using a URL argument or ?invoice_id=123.

    Requires CalculateOutstandingBalance in MySQL. Money is returned as a
    decimal string to preserve precision.
    """
    raw_id = invoice_id if invoice_id is not None else request.GET.get("invoice_id")
    if (isinstance(raw_id, bool) or not isinstance(raw_id, (str, int))
            or not str(raw_id).isascii() or not str(raw_id).isdigit()
            or len(str(raw_id)) > 10):
        return JsonResponse({"success": False, "error": "invoice_id must be a positive integer."}, status=400)
    invoice_id = int(raw_id)
    if not 0 < invoice_id <= 2147483647:
        return JsonResponse({"success": False, "error": "invoice_id is outside the valid range."}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT Invoice_id, CalculateOutstandingBalance(Invoice_id) "
                "FROM Invoice WHERE Invoice_id = %s", [invoice_id],
            )
            row = cursor.fetchone()
    except DatabaseError:
        logger.exception("Failed to retrieve outstanding balance")
        return JsonResponse({"success": False, "error": "Unable to retrieve outstanding balance."}, status=500)
    if row is None:
        return JsonResponse({"success": False, "error": "Invoice not found."}, status=404)
    return JsonResponse({"success": True, "invoice_id": row[0], "outstanding_balance": row[1]})
