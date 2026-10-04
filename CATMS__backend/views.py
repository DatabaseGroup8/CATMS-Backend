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
                        'status':'success', 
                        'data':{'outstanding_balance': float(row[0])}
                    }, status=200)
                else:
                    return JsonResponse({'status': 'error', 'message': 'Invoice not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)

# View 2: Record a Patient Payment
@csrf_exempt
def record_payment(request):
    if request.method =='POST':
        try:
            # Step 3: Parse the Frontend JSON Data
            data =json.loads(request.body)
            invoice_id= data.get('invoice_id')
            patient_id =data.get('patient_id')
            payment_amount =data.get('payment_amount')
            payment_method = data.get('payment_method')

            with connection.cursor() as cursor:
                # Execute the Stored Procedure using MySQL session variables for OUT parameters
                cursor.execute("""
                    CALL RecordPayment(%s, %s, %s, %s, @p_payment_id, @p_error_message, @p_success);
                """, [invoice_id, patient_id, payment_amount, payment_method])
                
                # Fetch the OUT parameters back from MySQL
                cursor.execute("SELECT @p_payment_id, @p_error_message, @p_success;")
                result = cursor.fetchone()
                p_payment_id, p_error_message, p_success = result
                
                if p_success:
                    return JsonResponse({
                        'status': 'success', 
                        'message': 'Payment recorded successfully',
                        'data': {'payment_id': p_payment_id}
                    }, status=200)
                else:
                    return JsonResponse({'status': 'error', 'message': p_error_message}, status=400)
                    
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)



# View 3:Process an Insurance Claim
@csrf_exempt
def process_insurance_claim(request):
    if request.method=='POST':
        try:
            data =json.loads(request.body)
            invoice_id =data.get('invoice_id')
            insurance_id =data.get('insurance_id')
            claim_amount = data.get('claim_amount')

            with connection.cursor() as cursor:
                # Call the Stored Procedure with OUT parameters
                cursor.execute("""
                    CALL ProcessInsuranceClaim(%s, %s, %s, @p_error_message, @p_success);
                """, [invoice_id, insurance_id, claim_amount])
                
                # Retrieve the success flag and error message
                cursor.execute("SELECT @p_error_message, @p_success;")
                result = cursor.fetchone()
                p_error_message, p_success = result
                
                if p_success:
                    return JsonResponse({'status': 'success', 'message': 'Claim processed successfully'}, status=200)
                else:
                    return JsonResponse({'status': 'error', 'message': p_error_message}, status=400)
                    
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)


# ---------------------------------------------------------
# Clinical Core View
# ---------------------------------------------------------
@csrf_exempt
def add_medication(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            with connection.cursor() as cursor:
                # Executes the AddMedication procedure designated for the Clinical Core[cite: 1]
                cursor.execute("CALL AddMedication(%s, %s, %s, %s)", 
                               [data['patient_id'], data['medication_name'], data['dosage'], data['frequency']])
            return JsonResponse({'status': 'success', 'message': 'Medication added successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

# ---------------------------------------------------------
# Registration View
# ---------------------------------------------------------
@csrf_exempt
def register_patient(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            with connection.cursor() as cursor:
                # Executes the RegisterPatient procedure designated for Identity & Access[cite: 1]
                # Patient records must include personal details, emergency contact, and insurance[cite: 4]
                cursor.execute("CALL RegisterPatient(%s, %s, %s, %s, %s)", 
                               [data['first_name'], data['last_name'], data['contact_number'], data['emergency_contact'], data['insurance_info']])
            return JsonResponse({'status': 'success', 'message': 'Patient registered successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

# ---------------------------------------------------------
# Billing View
# ---------------------------------------------------------
@csrf_exempt
def generate_invoice(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            with connection.cursor() as cursor:
                # Executes the GenerateInvoice procedure designated for the Financial Ledger[cite: 2]
                cursor.execute("CALL GenerateInvoice(%s)", 
                               [data['appointment_id']])
            return JsonResponse({'status': 'success', 'message': 'Invoice generated successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

# ---------------------------------------------------------
# Reporting View
# ---------------------------------------------------------
@csrf_exempt
def get_revenue_report(request):
    if request.method == 'GET':
        try:
            with connection.cursor() as cursor:
                # Generates the Doctor-wise revenue report required by the clinic management[cite: 5]
                cursor.execute("""
                    SELECT d.doctor_id, d.first_name, d.last_name, SUM(i.total_amount) as total_revenue
                    FROM Doctor d
                    JOIN Appointment a ON d.doctor_id = a.doctor_id
                    JOIN Invoice i ON a.appointment_id = i.appointment_id
                    GROUP BY d.doctor_id, d.first_name, d.last_name
                """)
                rows = cursor.fetchall()
                report_data = []
                for row in rows:
                    report_data.append({
                        'doctor_id': row[0],
                        'first_name': row[1],
                        'last_name': row[2],
                        'total_revenue': float(row[3]) if row[3] else 0.0
                    })
            return JsonResponse({'status': 'success', 'data': report_data}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)