import jwt
from django.conf import settings
from django.http import JsonResponse
from functools import wraps

def jwt_required(allowed_roles=None):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # 1. Get the token from the Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return JsonResponse({'error': 'Missing or invalid token'}, status=401)
                
            token = auth_header.split(' ')[1]
            
            try:
                # 2. Decrypt the token using your secret key
                decoded_payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                
                # 3. Attach the secure data to the request so the view can use it
                request.user_role = decoded_payload.get('role')
                request.branch_id = decoded_payload.get('branch_id')
                request.employee_id = decoded_payload.get('employee_id')
                
                # 4. Optional Role-Based Access Control (RBAC)
                if allowed_roles and request.user_role not in allowed_roles:
                    return JsonResponse({'error': 'Unauthorized role'}, status=403)
                    
            except jwt.ExpiredSignatureError:
                return JsonResponse({'error': 'Token has expired. Please log in again.'}, status=401)
            except jwt.InvalidTokenError:
                return JsonResponse({'error': 'Invalid token'}, status=401)
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator