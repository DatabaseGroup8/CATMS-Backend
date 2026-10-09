export type Role = 'Receptionist' | 'Doctor' | 'Branch Manager';
export type Staff = { full_name: string; role: Role };
export type Session = { user: Staff | null; csrf_token: string };
