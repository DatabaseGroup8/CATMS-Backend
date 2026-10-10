import json
import logging
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from accounts.decorators import jwt_required

logger = logging.getLogger(__name__)

def _catalogue(sql, params=None):
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()
        return JsonResponse({'status': 'success',
            'data': [dict(zip(columns, r)) for r in rows]})
    except DatabaseError:
        logger.exception('Catalogue read failed')
        return JsonResponse({'status': 'error',
                             'message': 'Unable to load catalogue'}, status=500)
        
@jwt_required(allowed_roles=['Receptionist', 'Doctor', 'Manager'])
@require_GET
def list_condition_categories(request):
    return _catalogue('''
        SELECT condition_category_id, category_name
        FROM Condition_category ORDER BY category_name
    ''')
    
@jwt_required(allowed_roles=['Receptionist', 'Doctor', 'Manager'])
@require_GET
def list_conditions(request):
    q = request.GET.get('q', '').strip()
    if len(q) > 100:
        return JsonResponse({'status': 'error',
                             'message': 'Query too long'}, status=400)
    return _catalogue('''
        SELECT c.condition_id, c.condition_name, c.description,
               c.condition_category_id, cc.category_name
        FROM Conditions c
        LEFT JOIN Condition_category cc
          ON cc.condition_category_id=c.condition_category_id
        WHERE c.condition_name LIKE %s
        ORDER BY c.condition_name LIMIT 100
    ''', [f'%{q}%'])

@jwt_required(allowed_roles=['Receptionist', 'Manager'])
@require_GET
def list_treatment_categories(request):
    return _catalogue('''
            SELECT treatment_category_id, category_name, description
        FROM Treatment_Category ORDER BY category_name
    ''')

@jwt_required(allowed_roles=['Receptionist', 'Doctor', 'Manager'])
@require_GET
def list_specializations(request):
    return _catalogue('''
        SELECT specialization_id, specialization_name, description
        FROM Specialization ORDER BY specialization_name
    ''')

@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
@require_POST
def assign_doctor_specialization(request, doctor_id):
    try:
        body = json.loads(request.body)
        specialization_id = body.get('specialization_id')
        if type(specialization_id) is not int or specialization_id <= 0:
            raise ValueError('Invalid specialization_id')
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'error',
                             'message': 'Invalid request'}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT 1 FROM Doctor d
                JOIN Employee e ON e.employee_id=d.employee_id
                WHERE d.doctor_id=%s
                  AND e.branch_id=%s AND e.role='Doctor'
                  AND e.status='Active'
                  AND EXISTS (
                     SELECT 1 FROM Employee m
                     WHERE m.employee_id=%s AND m.branch_id=%s
                       AND m.role='Manager' AND m.status='Active'
                  )
            ''', [doctor_id, request.branch_id,
                  request.employee_id, request.branch_id])
            if cursor.fetchone() is None:
                return JsonResponse({'status': 'error',
                    'message': 'Doctor not found in branch'}, status=404)
            cursor.execute('''
                SELECT 1 FROM Specialization
                WHERE specialization_id=%s
            ''', [specialization_id])
            if cursor.fetchone() is None:
                return JsonResponse({'status': 'error',
                    'message': 'Specialization not found'}, status=404)
            cursor.execute('''
                            INSERT IGNORE INTO Doctor_Specialization
                  (specialization_id, doctor_id) VALUES (%s,%s)
            ''', [specialization_id, doctor_id])
        return JsonResponse({'status': 'success',
                             'message': 'Assignment processed'})
    except DatabaseError:
        logger.exception('Specialization assignment failed')
        return JsonResponse({'status': 'error',
                             'message': 'Unable to assign'}, status=500)
                             