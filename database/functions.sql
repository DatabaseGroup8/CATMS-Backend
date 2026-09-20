DELIMITER //

-- Function 1: Generate Invoice Number
DROP FUNCTION IF EXISTS `GenerateInvoiceNumber`$$
CREATE FUNCTION `GenerateInvoiceNumber`()
RETURNS VARCHAR(20)
READS SQL DATA
BEGIN
    DECLARE v_invoice_count INT;
    DECLARE v_invoice_number VARCHAR(20);
    
    -- Count invoices created today to append a daily sequence
    SELECT COUNT(*) + 1 INTO v_invoice_count
    FROM Invoice 
    WHERE DATE(date) = CURDATE(); 
    
    -- Format: INV-20260919-0001
    SET v_invoice_number = CONCAT('INV-', DATE_FORMAT(CURDATE(), '%Y%m%d'), '-', LPAD(v_invoice_count, 4, '0'));
    
    RETURN v_invoice_number;
END//

-- Function 2: Calculate Outstanding Balance
DROP FUNCTION IF EXISTS `CalculateOutstandingBalance`$$
CREATE FUNCTION `CalculateOutstandingBalance`(p_invoice_id INT)
RETURNS DECIMAL(10,2)
READS SQL DATA
BEGIN
    DECLARE v_sub_total DECIMAL(10,2) DEFAULT 0.00;
    DECLARE v_insurance_claimed DECIMAL(10,2) DEFAULT 0.00;
    DECLARE v_total_paid DECIMAL(10,2) DEFAULT 0.00;
    
    -- Get base bill and insurance deductions[cite: 1]
    SELECT sub_total, COALESCE(insurance_claimed_amount, 0)
    INTO v_sub_total, v_insurance_claimed
    FROM Invoice
    WHERE invoice_id = p_invoice_id;
    
    -- Sum all successful payments made towards this invoice
    -- Note: Assumes a 'payment_amount' column is added to Payment table--There is no payment amount column
    SELECT COALESCE(SUM(payment_amount), 0) 
    INTO v_total_paid
    FROM Payment
    WHERE invoice_id = p_invoice_id AND status = 'Completed';
    
    -- Return what the patient still owes[cite: 2]
    RETURN v_sub_total - v_insurance_claimed - v_total_paid;
END$$

--Function 3: GetConsultationDuration
CREATE FUNCTION GetConsultationDuration(p_consultation_id INT) 
RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_duration_minutes INT;

    -- Calculate the difference in minutes between end_time and start_time
    SELECT TIMESTAMPDIFF(MINUTE, ts.start_time, ts.end_time) INTO v_duration_minutes
    FROM Consultation_record cr
    JOIN Appointment a ON cr.appointment_id = a.appointment_id
    JOIN Time_Slot ts ON a.time_slot_id = ts.time_slot_id
    WHERE cr.consultation_record_id = p_consultation_id;

    -- Return the calculated duration (or 0 if not found)
    RETURN COALESCE(v_duration_minutes, 0);
END //

DELIMITER ;

--Function 4: Check Doctor Availability
DROP FUNCTION IF EXISTS IsDoctorAvailable$$
CREATE FUNCTION IsDoctorAvailable(
    p_doctor_id INT,
    p_date DATE,
    p_time TIME
)
RETURNS BOOLEAN
READS SQL DATA
BEGIN
    DECLARE slot_available INT;
    
    SELECT COUNT(*) INTO slot_available
    FROM time_slot
    WHERE doctor_id = p_doctor_id
    AND available_date = p_date
    AND start_time <= p_time
    AND end_time > p_time
    AND is_booked = FALSE;
    
    RETURN slot_available > 0;
END$$


