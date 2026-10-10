from django.shortcuts import render
import json
import jwt
import datetime
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import connection
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from .decorators import jwt_required

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def login_view(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        raw_password = data.get('password')
        selected_branch = data.get('branch_id')
        
        # 1. Basic validation
        if not all([email, raw_password, selected_branch]):
            return JsonResponse({
                'status': 'error', 
                'message': 'Branch, email, and password are required.'
            }, status=400)

        with connection.cursor() as cursor:
            # 2. Join User and Employee tables to verify identity and branch assignment[cite: 3]
            cursor.execute("""
                SELECT 
                    e.employee_id, 
                    e.role, 
                    u.full_name, 
                    u.Password_hash
                FROM User u
                JOIN Employee e ON u.user_id = e.user_id
                WHERE u.email = %s 
                  AND e.branch_id = %s 
                  AND e.status = 'Active'
            """, [email, selected_branch])
            
            user_record = cursor.fetchone()

        # 3. Verify the password hash[cite: 3]
        # user_record[3] contains the hashed password stored in the database
        if user_record and check_password(raw_password, user_record[3]):
            
            # 4. Generate the JWT Payload
            token_payload = {
                'employee_id': user_record[0],
                'role': user_record[1],
                'branch_id': selected_branch,
                # Set token expiration (e.g., 8 hours)
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=8)
            }
            
            # 5. Cryptographically sign the token using Django's secret key
            encoded_jwt = jwt.encode(token_payload, settings.SECRET_KEY, algorithm='HS256')
            
            return JsonResponse({
                'status': 'success',
                'message': 'Authentication successful.',
                'token': encoded_jwt,
                'data': {
                    'employee_id': user_record[0],
                    'full_name': user_record[2],
                    'role': user_record[1],
                    'active_branch_id': selected_branch
                }
            }, status=200)
            
        # If the user is not found, the branch is wrong, or the password doesn't match
        return JsonResponse({
            'status': 'error', 
            'message': 'Invalid credentials or unauthorized for this branch.'
        }, status=401)
        
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)
    except Exception as e:
        logger.exception("Login failed")
        return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
    
    
    
@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Manager'])
def register_doctor(request):
    try:
        data = json.loads(request.body)
        
        # 1. Securely extract branch from JWT
        manager_branch_id = request.branch_id
        
        # 2. Hash the password
        raw_password = data.get('password')
        if not raw_password:
            return JsonResponse({'status': 'error', 'message': 'Password is required.'}, status=400)
            
        secure_hashed_password = make_password(raw_password)
        
        with connection.cursor() as cursor:
            cursor.execute("SET @p_doctor_id = NULL, @p_employee_id = NULL, @p_user_id = NULL, @p_success = 0, @p_message = NULL;")
            
            # 3. Pass the hashed password to the RegisterDoctor procedure[cite: 5]
            cursor.execute("""
                CALL RegisterDoctor(
                    %s, %s, %s, %s, %s, 
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    @p_doctor_id, @p_employee_id, @p_user_id, @p_success, @p_message
                )
            """, [
                data.get('address_line_1'), data.get('address_line_2'), data.get('city'), data.get('province'), data.get('postal_code'),
                data.get('full_name'), data.get('NIC'), data.get('gender'), data.get('DOB'), data.get('email'), data.get('contact_no'), 
                secure_hashed_password, # INJECT HASHED PASSWORD HERE
                manager_branch_id,      # INJECT MANAGER'S BRANCH ID HERE
                data.get('salary'), data.get('joined_date'),
                data.get('room_no'), data.get('medical_licence_number')
            ])
            
            while cursor.nextset(): pass
            cursor.execute("SELECT @p_doctor_id, @p_employee_id, @p_user_id, @p_success, @p_message;")
            doc_id, emp_id, user_id, success, message = cursor.fetchone()

        if success:
            return JsonResponse({'status': 'success', 'message': message, 'doctor_id': doc_id}, status=201)
        return JsonResponse({'status': 'error', 'message': message}, status=400)
        
    except Exception as e:
        return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
    
    


@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Manager'])
def register_staff(request):
    try:
        data = json.loads(request.body)
        
        # 1. Branch is now securely provided by the decrypted JWT
        manager_branch_id = request.branch_id
        
        # 2. Extract the raw password from the frontend and hash it
        raw_password = data.get('password')
        if not raw_password:
            return JsonResponse({'status': 'error', 'message': 'Password is required.'}, status=400)
            
        secure_hashed_password = make_password(raw_password)
        
        with connection.cursor() as cursor:
            cursor.execute("SET @p_employee_id = NULL, @p_user_id = NULL, @p_success = 0, @p_message = NULL;")
            
            # 3. Pass the hashed password to the RegisterEmployee procedure[cite: 5]
            cursor.execute("""
                CALL RegisterEmployee(
                    %s, %s, %s, %s, %s, 
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    @p_employee_id, @p_user_id, @p_success, @p_message
                )
            """, [
                data.get('address_line_1'), data.get('address_line_2'), data.get('city'), data.get('province'), data.get('postal_code'),
                data.get('full_name'), data.get('NIC'), data.get('gender'), data.get('DOB'), data.get('email'), data.get('contact_no'), 
                secure_hashed_password, # INJECT HASHED PASSWORD HERE
                manager_branch_id,      # INJECT MANAGER'S BRANCH ID HERE
                data.get('role'), data.get('salary'), data.get('joined_date')
            ])
            
            while cursor.nextset(): pass
            cursor.execute("SELECT @p_employee_id, @p_user_id, @p_success, @p_message;")
            emp_id, user_id, success, message = cursor.fetchone()

        if success:
            return JsonResponse({'status': 'success', 'message': message, 'employee_id': emp_id}, status=201)
        return JsonResponse({'status': 'error', 'message': message}, status=400)
        
    except Exception as e:
        return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
    
    

