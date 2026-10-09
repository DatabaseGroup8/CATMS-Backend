from django.shortcuts import render
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.db import DatabaseError, connection
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

@csrf_exempt
def process_full_checkout(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            patient_id = data.get('patient_id')
            total_amount = data.get('total_amount')
            payment_amount = data.get('payment_amount')
            
            if not patient_id or not total_amount or payment_amount is None:
                return JsonResponse({'status': 'error', 'message': 'Missing billing data.'}, status=400)

            with connection.cursor() as cursor:
                # Step 1: Create the Invoice FIRST
                # (You mentioned a GenerateInvoiceNumber function earlier; you can call it here if needed)
                cursor.execute("""
                    INSERT INTO Invoice (patient_id, total_amount, created_at) 
                    VALUES (%s, %s, CURDATE());
                """, [patient_id, total_amount])
                
                # Retrieve the new Invoice ID
                cursor.execute("SELECT LAST_INSERT_ID();")
                invoice_id = cursor.fetchone()[0]

                # Step 2: Create the Payment immediately after, using the new Invoice ID
                cursor.execute("""
                    INSERT INTO Payment (invoice_id, payment_amount) 
                    VALUES (%s, %s);
                """, [invoice_id, payment_amount])
                
                # Retrieve the new Payment ID
                cursor.execute("SELECT LAST_INSERT_ID();")
                payment_id = cursor.fetchone()[0]

            return JsonResponse({
                'status': 'success',
                'message': 'Invoice generated and payment processed.',
                'invoice_id': invoice_id,
                'payment_id': payment_id,
                'balance_remaining': float(total_amount) - float(payment_amount)
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
    #Prefer the URL argument, falling back to the invoice_id query parameter.
    raw_id = invoice_id if invoice_id is not None else request.GET.get("invoice_id")

    # Validate before conversion, including a length limit for oversized inputs.
    if (isinstance(raw_id, bool) or not isinstance(raw_id, (str, int))
            or not str(raw_id).isascii() or not str(raw_id).isdigit()
            or len(str(raw_id)) > 10):
        return JsonResponse({"success": False, "error": "invoice_id must be a positive integer."}, status=400)
    invoice_id = int(raw_id)

    # Invoice IDs use a signed MySQL INT column.
    if not 0 < invoice_id <= 2147483647:
        return JsonResponse({"success": False, "error": "invoice_id is outside the valid range."}, status=400)
    try:
        with connection.cursor() as cursor:
            # Select from Invoice so a missing invoice produces no row.
            # The SQL function deducts insurance and completed payments.
            cursor.execute(
                "SELECT Invoice_id, CalculateOutstandingBalance(Invoice_id) "
                "FROM Invoice WHERE Invoice_id = %s", [invoice_id],
            )
            row = cursor.fetchone()
    except DatabaseError:
        logger.exception("Failed to retrieve outstanding balance")
        return JsonResponse({"success": False, "error": "Unable to retrieve outstanding balance."}, status=500)
    # Distinguish an unknown invoice from an existing invoice with zero balance.
    if row is None:
        return JsonResponse({"success": False, "error": "Invoice not found."}, status=404)
    # JsonResponse encodes Decimal as a string, preserving monetary precision.
    return JsonResponse({"success": True, "invoice_id": row[0], "outstanding_balance": row[1]})
