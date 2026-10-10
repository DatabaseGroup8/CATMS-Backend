"""Manager setup endpoints: create insurance package and assign patient coverage.
Existing AddPatientInsurance procedure reused. Review authorization rules if your
clinic allows managers to manage patients beyond their branch.
"""
import logging
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from accounts.decorators import jwt_required
from .workflow_common import (
    bad, payload, positive_int, text_value, amount, parse_date,
    call_out,
)

logger = logging.getLogger(__name__)


def _manager_branch(cursor, request):
    employee_id = positive_int(request.employee_id, 'employee_id')
    branch_id = positive_int(request.branch_id, 'branch_id')
    cursor.execute("""
        SELECT COUNT(*) FROM Employee e WHERE e.employee_id=%s AND e.branch_id=%s
          AND e.role='Manager' AND e.status='Active'
    """, [employee_id, branch_id])
    if cursor.fetchone()[0] != 1:
        raise PermissionError('Manager is not active for this branch')
    return branch_id


@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
@require_POST
def create_insurance_package(request):
    try:
        data=payload(request)
        name=text_value(data.get('package_name'), 'package_name',50,True)
        annual_name=text_value(data.get('annual_name'), 'annual_name',50)
        copay=amount(data.get('copayment_percentage'),'copayment_percentage',allow_zero=True)
        if copay > 100:
            raise ValueError('copayment_percentage must be 0..100')
        started=parse_date(data.get('started_date'))
    except ValueError as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            _manager_branch(cursor,request)
            cursor.execute("""
                INSERT INTO Insurance_Packages
                    (package_name,annual_name,copayment_percentage,started_date,updated_date)
                VALUES (%s,%s,%s,%s,CURDATE())
            """,[name,annual_name,copay,started])
            package_id=cursor.lastrowid
    except PermissionError as exc:
        return bad(str(exc),403)
    except DatabaseError:
        logger.exception('Insurance package insertion failed')
        return bad('Unable to create insurance package',500)
    return JsonResponse({'status':'success','insurance_package_id':package_id},status=201)


@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
@require_POST
def assign_patient_insurance(request):
    try:
        data=payload(request)
        patient_id=positive_int(data.get('patient_id'),'patient_id')
        package_id=positive_int(data.get('insurance_package_id'),'insurance_package_id')
        start=parse_date(data.get('started_date'))
        end=parse_date(data.get('end_date'))
        if end<=start:
            raise ValueError('end_date must be later than started_date')
    except ValueError as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            branch_id=_manager_branch(cursor,request)
            # Authorize a patient registered at this branch or who visited this branch.
            cursor.execute("""
                SELECT COUNT(*) FROM Patient p WHERE p.patient_id=%s
                AND (p.registered_branch_id=%s OR EXISTS (
                    SELECT 1 FROM Appointment a
                    JOIN Time_Slot ts ON a.time_slot_id=ts.time_slot_id
                    WHERE a.patient_id=p.patient_id AND ts.branch_id=%s
                ))
            """,[patient_id,branch_id,branch_id])
            if cursor.fetchone()[0] != 1:
                return bad('Patient not available for this branch',404)
            insurance_id,message,success=call_out(
                cursor,
                'CALL AddPatientInsurance(%s,%s,%s,%s,%s,@ins_id,@ins_msg,@ins_ok)',
                [patient_id,package_id,start,end,'Active'],
                'SELECT @ins_id,@ins_msg,@ins_ok'
            )
    except PermissionError as exc:
        return bad(str(exc),403)
    except DatabaseError:
        logger.exception('Patient insurance assignment failed')
        return bad('Could not assign insurance',500)
    if not success:
        logger.warning('AddPatientInsurance failed: %s',message)
        return bad('Insurance could not be assigned',409)
    return JsonResponse({'status':'success','insurance_id':insurance_id},status=201)
