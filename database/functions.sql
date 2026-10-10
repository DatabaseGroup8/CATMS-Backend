-- CATMS functions, fresh install, MySQL 8.0.16+
-- Run AFTER tables.sql and BEFORE procedures.sql/triggers.sql.
-- Intentional source spelling preserved: CaculateInsuranceCoverage.
DELIMITER $$

CREATE FUNCTION IsValidEmail(p_email VARCHAR(255)) RETURNS BOOLEAN
DETERMINISTIC NO SQL
BEGIN
    RETURN p_email IS NOT NULL AND
           p_email REGEXP '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$';
END$$

CREATE FUNCTION CalculateAge(p_dob DATE) RETURNS INT
NOT DETERMINISTIC NO SQL
BEGIN
    IF p_dob IS NULL THEN RETURN NULL; END IF;
    RETURN TIMESTAMPDIFF(YEAR,p_dob,CURDATE());
END$$

CREATE FUNCTION CountPatientAppointments(p_patient_id INT,p_status VARCHAR(50)) RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_count INT DEFAULT 0;
    SELECT COUNT(*) INTO v_count FROM Appointment
      WHERE patient_id=p_patient_id AND (p_status IS NULL OR status=p_status);
    RETURN v_count;
END$$

CREATE FUNCTION GetConsultationDuration(p_consultation_id INT) RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_minutes INT DEFAULT 0;
    SELECT TIMESTAMPDIFF(MINUTE,
               TIMESTAMP(ts.available_date,ts.start_time),
               TIMESTAMP(ts.available_date,ts.end_time))
      INTO v_minutes FROM consultation_record cr
      JOIN Appointment a ON a.appointment_id=cr.appointment_id
      JOIN Time_Slot ts ON a.time_slot_id=ts.time_slot_id
      WHERE cr.consultation_rec_id=p_consultation_id;
    RETURN COALESCE(v_minutes,0);
END$$

-- This only reflects the legacy is_booked flag; no slot capacity in current schema.
CREATE FUNCTION IsDoctorAvailable(
    p_doctor_id INT, p_date DATE, p_time TIME
) RETURNS BOOLEAN
READS SQL DATA
BEGIN
    DECLARE v_count INT DEFAULT 0;
    SELECT COUNT(*) INTO v_count
    FROM Time_Slot
    WHERE doctor_id = p_doctor_id
      AND available_date = p_date
      AND start_time <= p_time
      AND end_time > p_time
      AND available = TRUE;
    RETURN v_count > 0;
END$$

CREATE FUNCTION IsInsuranceActive(p_insurance_id INT) RETURNS BOOLEAN
READS SQL DATA
BEGIN
    DECLARE v_active BOOLEAN DEFAULT FALSE;
    SELECT (status='Active' AND started_date<=CURDATE()
        AND (end_date IS NULL OR end_date>=CURDATE()))
      INTO v_active FROM Insurance WHERE Insurance_id=p_insurance_id;
    RETURN COALESCE(v_active,FALSE);
END$$

CREATE FUNCTION CaculateInsuranceCoverage(p_amount DECIMAL(10,2),p_copayment_percentage DECIMAL(10,2))
RETURNS DECIMAL(10,2) DETERMINISTIC NO SQL
BEGIN
    IF p_amount IS NULL OR p_amount<0 OR p_copayment_percentage IS NULL
       OR p_copayment_percentage<0 OR p_copayment_percentage>100 THEN
        RETURN NULL;
    END IF;
    RETURN ROUND(p_amount*(100-p_copayment_percentage)/100,2);
END$$

CREATE FUNCTION CalculateMedicationTotal(p_medical_record_id INT) RETURNS DECIMAL(12,2)
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(12,2) DEFAULT 0.00;
    SELECT COALESCE(SUM(quantity*unit_price),0.00) INTO v_total
       FROM Prescription WHERE medical_record_id=p_medical_record_id;
    RETURN v_total;
END$$

CREATE FUNCTION CalculateTreatmentTotal(p_medical_record_id INT) RETURNS DECIMAL(12,2)
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(12,2) DEFAULT 0.00;
    SELECT COALESCE(SUM(unit_price),0.00) INTO v_total
      FROM Treatment WHERE medical_record_id=p_medical_record_id;
    RETURN v_total;
END$$

CREATE FUNCTION CalculateEligibleTreatmentTotal(p_invoice_id INT) RETURNS DECIMAL(12,2)
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(12,2) DEFAULT 0.00;
    SELECT COALESCE(SUM(t.unit_price),0.00) INTO v_total
    FROM Invoice i JOIN consultation_record cr ON cr.appointment_id=i.appointment_id
    JOIN Treatment t ON t.medical_record_id=cr.medical_record_id
    WHERE i.Invoice_id=p_invoice_id AND t.insurance_eligible=TRUE;
    RETURN v_total;
END$$

CREATE FUNCTION CalculateOutstandingBalance(p_invoice_id INT) RETURNS DECIMAL(12,2)
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(12,2) DEFAULT NULL;
    SELECT i.sub_total - COALESCE(i.insurance_claimed_amount,0) -
      COALESCE((SELECT SUM(p.payment_amount) FROM Payment p
        WHERE p.Invoice_id=i.Invoice_id AND p.status='Completed'),0)
      INTO v_total FROM Invoice i WHERE i.Invoice_id=p_invoice_id;
    RETURN v_total; -- NULL if invoice does not exist
END$$
DELIMITER ;
