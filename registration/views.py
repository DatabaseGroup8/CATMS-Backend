from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

@csrf_exempt
def search_patients(request):
    # Step 1: Enforce GET method since we are reading data
    if request.method == 'GET':
        # Grab the search term from the URL (e.g., /api/registration/search/?q=Kamal)
        # Defaults to an empty string if no search term is provided
        search_query = request.GET.get('q', '')
        
        try:
            with connection.cursor() as cursor:
                # Add SQL wildcards (%) to find partial matches anywhere in the string
                search_pattern = f"%{search_query}%"
                
                # Step 2: Execute raw SQL with the LIKE operator
                cursor.execute("""
                    SELECT 
                        patient_id, 
                        first_name, 
                        last_name, 
                        date_of_birth, 
                        contact_number
                    FROM Patient
                    WHERE first_name LIKE %s 
                       OR last_name LIKE %s 
                       OR contact_number LIKE %s
                    ORDER BY first_name ASC
                    LIMIT 50;
                """, [search_pattern, search_pattern, search_pattern])
                
                # Step 3: Fetch all matching rows
                rows = cursor.fetchall()
                
            # Step 4: Map the raw tuple data into a JSON-friendly list of dictionaries
            patients_list = []
            for row in rows:
                patients_list.append({
                    'patient_id': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    # Convert date object to a standard string format
                    'date_of_birth': row[3].strftime('%Y-%m-%d') if row[3] else None,
                    'contact_number': row[4]
                })

            # Step 5: Return the payload
            return JsonResponse({
                'status': 'success',
                'results_count': len(patients_list),
                'data': patients_list
            }, status=200)

        except Exception as e:
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method is allowed'}, status=405)
