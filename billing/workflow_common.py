"""Shared helpers for the CATMS plain-Django + MySQL stored procedure APIs."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse


def bad(message, status=400):
    return JsonResponse({'status': 'error', 'message': message}, status=status)


def payload(request):
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('Invalid JSON body') from exc
    if not isinstance(data, dict):
        raise ValueError('Expected JSON object')
    return data


def positive_int(value, name):
    if type(value) is not int or not (1 <= value <= 2147483647):
        raise ValueError(f'{name} must be a positive integer')
    return value


def text_value(value, name, limit=None, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a string')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{name} is required')
    if limit is not None and len(value) > limit:
        raise ValueError(f'{name} is too long')
    return value


def amount(value, name, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f'{name} must be a decimal string')
    try:
        money = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'Invalid {name}') from exc
    if not money.is_finite() or money.as_tuple().exponent < -2 or money > Decimal('99999999.99'):
        raise ValueError(f'Invalid {name}')
    if money < 0 or (money == 0 and not allow_zero):
        raise ValueError(f'{name} must be positive')
    return money


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError('date is required in YYYY-MM-DD format')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('Invalid date (YYYY-MM-DD required)') from exc


def call_out(cursor, sql, params, out_select):
    """CALL stored procedure and drain result sets before SELECTing OUT variables.

    Procedure already contains transaction management; do NOT wrap in atomic().
    SQL strings are constants written in server code, not user input.
    """
    cursor.execute(sql, params)
    while cursor.nextset():
        pass
    cursor.execute(out_select)
    return cursor.fetchone()


ALLOWED_PROCEDURE_MESSAGES = {
    'Doctor not authorized for appointment',
    'Only Scheduled appointments can be completed',
    'Appointment must be Completed',
    'Unauthorized receptionist/branch',
    'Consultation or invoice already finalized',
    'Chief complaint and diagnosis required',
    'Items must be JSON arrays',
    'At least one billable item is required',
    'Too many consultation items',
    'Invalid medication item',
    'Invalid medication ID',
    'Invalid medication quantity',
    'Medication quantity too large',
    'Incomplete dosage/frequency/duration',
    'Medication missing or price invalid',
    'Invalid treatment code',
    'Treatment missing or price invalid',
    'Invoice subtotal invalid',
    'Completed invoice not found',
    'Invoice amount invalid',
    'Insurance already applied to invoice',
    'Apply insurance before patient payments',
    'No eligible active insurance for patient',
    'No insurance-eligible treatments',
    'Calculated insurance amount invalid',
    'Invalid payment amount/method/request key',
    'Payment request key reused for different details',
    'Payment exceeds patient outstanding balance',
    'Manager unauthorized',
    'Claim not pending',
    'Invalid approved amount',
    'Invoice not found',
    'Insurance claim not approved',
    'Settlement exceeds approved amount',
    'Settlement amount must be positive',
    'Generic name is required',
    'Medication price is required',
    'Medication already exists',
}


def procedure_failed(logger, operation, message):
    logger.warning('Procedure %s unsuccessful: %s', operation, message)
    safe = message if message in ALLOWED_PROCEDURE_MESSAGES else 'Operation could not be completed'
    return bad(safe, 409)
