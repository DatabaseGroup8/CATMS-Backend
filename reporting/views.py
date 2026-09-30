from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

@csrf_exempt
def get_doctor_performance_report(request):
    # Step 1: Enforce GET method since we are only reading data
    if request.method == 'GET':
        try:
            # Step 2: Open a secure database cursor
            with connection.cursor() as cursor:
                
                # Step 3: Execute the analytical SQL query
                cursor.execute("""
                    SELECT 
                        d.doctor_id,
                        d.first_name,
                        d.last_name,
                        d.specialization,
                        COUNT(a.appointment_id) AS total_appointments,
                        SUM(CASE WHEN a.status = 'Completed' THEN 1 ELSE 0 END) AS completed_appointments,
                        SUM(CASE WHEN a.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_appointments
                    FROM Doctor d
                    LEFT JOIN Time_Slot ts ON d.doctor_id = ts.doctor_id
                    LEFT JOIN Appointment a ON ts.time_slot_id = a.time_slot_id
                    GROUP BY 
                        d.doctor_id, 
                        d.first_name, 
                        d.last_name, 
                        d.specialization
                    ORDER BY completed_appointments DESC;
                """)
                
                # Step 4: Fetch all aggregated rows
                rows = cursor.fetchall()

            # Step 5: Format the raw tuple data into a JSON-friendly list of dictionaries
            performance_data = []
            for row in rows:
                performance_data.append({
                    'doctor_id': row[0],
                    'doctor_name': f"Dr. {row[1]} {row[2]}",
                    'specialization': row[3],
                    'total_appointments': row[4],
                    # Convert Decimal/None types safely to integers
                    'completed_appointments': int(row[5]) if row[5] else 0,
                    'cancelled_appointments': int(row[6]) if row[6] else 0
                })

            # Step 6: Return the payload
            return JsonResponse({
                'status': 'success',
                'doctor_count': len(performance_data),
                'data': performance_data
            }, status=200)

        except Exception as e:
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method is allowed'}, status=405)
