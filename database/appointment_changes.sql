-- CATMS appointment management extension for an ALREADY POPULATED MySQL 8 database.
-- Safe to re-run: creates the audit table if missing and replaces only these TWO procedures.
-- Select your existing database first, e.g. USE catms_local;
-- Prerequisite: the original tables.sql + procedures.sql are already installed.

CREATE TABLE IF NOT EXISTS Appointment_Change_Audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    changed_by_employee_id INT NOT NULL,
    change_type ENUM('Rescheduled', 'Cancelled') NOT NULL,
    old_time_slot_id INT,
    new_time_slot_id INT,
    old_status VARCHAR(50) NOT NULL,
    new_status VARCHAR(50) NOT NULL,
    old_queue_number INT NOT NULL,
    new_queue_number INT NOT NULL,
    reason VARCHAR(500),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_appt_audit_appointment FOREIGN KEY (appointment_id)
        REFERENCES Appointment(appointment_id),
    CONSTRAINT fk_appt_audit_actor FOREIGN KEY (changed_by_employee_id)
        REFERENCES Employee(employee_id),
    CONSTRAINT fk_appt_audit_old_slot FOREIGN KEY (old_time_slot_id)
        REFERENCES Time_Slot(time_slot_id),
    CONSTRAINT fk_appt_audit_new_slot FOREIGN KEY (new_time_slot_id)
        REFERENCES Time_Slot(time_slot_id),
    INDEX idx_appt_audit_appointment (appointment_id, changed_at)
) ENGINE=InnoDB;

DELIMITER $$

DROP PROCEDURE IF EXISTS RescheduleAppointment$$
CREATE PROCEDURE RescheduleAppointment(
    IN p_appointment_id INT,
    IN p_new_time_slot_id INT,
    IN p_receptionist_id INT,
    IN p_branch_id INT,
    IN p_reason VARCHAR(500),
    OUT p_new_queue_number INT,
    OUT p_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_old_slot_id INT DEFAULT NULL;
    DECLARE v_old_branch_id INT DEFAULT NULL;
    DECLARE v_patient_id INT DEFAULT NULL;
    DECLARE v_old_status VARCHAR(50) DEFAULT NULL;
    DECLARE v_old_number INT DEFAULT NULL;
    DECLARE v_new_branch_id INT DEFAULT NULL;
    DECLARE v_new_date DATE DEFAULT NULL;
    DECLARE v_new_available BOOLEAN DEFAULT NULL;
    DECLARE v_authorized INT DEFAULT 0;
    DECLARE v_active_doctor INT DEFAULT 0;
    DECLARE v_duplicate INT DEFAULT 0;
    DECLARE v_next_number INT DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
        SET p_new_queue_number = NULL;
    END;

    SET p_success = FALSE;
    SET p_message = NULL;
    SET p_new_queue_number = NULL;

    IF p_appointment_id IS NULL OR p_appointment_id <= 0
       OR p_new_time_slot_id IS NULL OR p_new_time_slot_id <= 0
       OR p_receptionist_id IS NULL OR p_branch_id IS NULL
       OR CHAR_LENGTH(COALESCE(p_reason, '')) > 500 THEN
        SET p_message = 'Invalid reschedule request';
        LEAVE proc_label;
    END IF;

    START TRANSACTION;

    -- Lock the existing appointment and its original session.
    SELECT a.patient_id, a.time_slot_id, a.status, a.appointment_number, ts.branch_id
      INTO v_patient_id, v_old_slot_id, v_old_status, v_old_number, v_old_branch_id
      FROM Appointment a
      JOIN Time_Slot ts ON ts.time_slot_id = a.time_slot_id
     WHERE a.appointment_id = p_appointment_id
     FOR UPDATE;

    IF v_old_slot_id IS NULL THEN
        SET p_message = 'Appointment not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    SELECT COUNT(*) INTO v_authorized FROM Employee e
     WHERE e.employee_id = p_receptionist_id AND e.branch_id = p_branch_id
       AND e.role = 'Receptionist' AND e.status = 'Active';
    IF v_authorized = 0 OR v_old_branch_id <> p_branch_id THEN
        SET p_message = 'Receptionist cannot modify appointments in this branch';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF v_old_status IS NULL OR v_old_status <> 'Scheduled' THEN
        SET p_message = 'Only Scheduled appointments may be rescheduled';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF v_old_slot_id = p_new_time_slot_id THEN
        SET p_message = 'Choose a different time slot';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Serializes concurrent bookings/reschedules into the same session.
    SELECT ts.branch_id, ts.available_date, ts.available
      INTO v_new_branch_id, v_new_date, v_new_available
      FROM Time_Slot ts
     WHERE ts.time_slot_id = p_new_time_slot_id
     FOR UPDATE;

    IF v_new_branch_id IS NULL THEN
        SET p_message = 'New time slot not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF v_new_branch_id <> p_branch_id THEN
        SET p_message = 'New time slot must belong to the same branch';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF v_new_date < CURDATE() OR v_new_available <> 1 THEN
        SET p_message = 'New time slot must be available and not in the past';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    SELECT COUNT(*) INTO v_active_doctor
      FROM Time_Slot ts JOIN Doctor d ON d.doctor_id = ts.doctor_id
      JOIN Employee e ON e.employee_id = d.employee_id
     WHERE ts.time_slot_id = p_new_time_slot_id
       AND e.branch_id = p_branch_id AND e.role = 'Doctor' AND e.status = 'Active';
    IF v_active_doctor = 0 THEN
        SET p_message = 'Attending doctor is not active in this branch';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    SELECT COUNT(*) INTO v_duplicate FROM Appointment
     WHERE patient_id = v_patient_id AND time_slot_id = p_new_time_slot_id
       AND status = 'Scheduled' AND appointment_id <> p_appointment_id;
    IF v_duplicate > 0 THEN
        SET p_message = 'Patient already has a Scheduled appointment in that time slot';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Preserve the original appointment ID, patient, type, notes and created_at.
    -- Historical queue numbers are recorded in the audit table.
    SELECT COALESCE(MAX(appointment_number), 0) + 1
      INTO v_next_number FROM Appointment WHERE time_slot_id = p_new_time_slot_id;

    UPDATE Appointment SET time_slot_id = p_new_time_slot_id,
        appointment_number = v_next_number, updated_at = CURDATE()
     WHERE appointment_id = p_appointment_id;

    INSERT INTO Appointment_Change_Audit (
        appointment_id, changed_by_employee_id, change_type,
        old_time_slot_id, new_time_slot_id, old_status, new_status,
        old_queue_number, new_queue_number, reason
    ) VALUES (
        p_appointment_id, p_receptionist_id, 'Rescheduled',
        v_old_slot_id, p_new_time_slot_id, 'Scheduled', 'Scheduled',
        v_old_number, v_next_number, NULLIF(TRIM(p_reason), '')
    );

    COMMIT;
    SET p_new_queue_number = v_next_number;
    SET p_success = TRUE;
    SET p_message = 'Appointment rescheduled successfully';
END$$

DROP PROCEDURE IF EXISTS CancelAppointment$$
CREATE PROCEDURE CancelAppointment(
    IN p_appointment_id INT,
    IN p_receptionist_id INT,
    IN p_branch_id INT,
    IN p_reason VARCHAR(500),
    OUT p_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_slot_id INT DEFAULT NULL;
    DECLARE v_slot_branch_id INT DEFAULT NULL;
    DECLARE v_status VARCHAR(50) DEFAULT NULL;
    DECLARE v_old_number INT DEFAULT NULL;
    DECLARE v_authorized INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    SET p_success = FALSE;
    SET p_message = NULL;
    IF p_appointment_id IS NULL OR p_appointment_id <= 0
       OR p_receptionist_id IS NULL OR p_branch_id IS NULL
       OR p_reason IS NULL OR CHAR_LENGTH(TRIM(p_reason)) < 3
       OR CHAR_LENGTH(p_reason) > 500 THEN
        SET p_message = 'Cancellation reason must contain at least 3 characters';
        LEAVE proc_label;
    END IF;

    START TRANSACTION;
    SELECT a.time_slot_id, a.status, a.appointment_number, ts.branch_id
      INTO v_slot_id, v_status, v_old_number, v_slot_branch_id
      FROM Appointment a JOIN Time_Slot ts ON ts.time_slot_id = a.time_slot_id
     WHERE a.appointment_id = p_appointment_id
     FOR UPDATE;

    IF v_slot_id IS NULL THEN
        SET p_message = 'Appointment not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    SELECT COUNT(*) INTO v_authorized FROM Employee e
     WHERE e.employee_id = p_receptionist_id AND e.branch_id = p_branch_id
       AND e.role = 'Receptionist' AND e.status = 'Active';
    IF v_authorized = 0 OR v_slot_branch_id <> p_branch_id THEN
        SET p_message = 'Receptionist cannot modify appointments in this branch';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF v_status IS NULL OR v_status <> 'Scheduled' THEN
        SET p_message = 'Only Scheduled appointments may be cancelled';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    UPDATE Appointment SET status = 'Cancelled', updated_at = CURDATE()
     WHERE appointment_id = p_appointment_id;

    INSERT INTO Appointment_Change_Audit (
        appointment_id, changed_by_employee_id, change_type,
        old_time_slot_id, new_time_slot_id, old_status, new_status,
        old_queue_number, new_queue_number, reason
    ) VALUES (
        p_appointment_id, p_receptionist_id, 'Cancelled',
        v_slot_id, v_slot_id, 'Scheduled', 'Cancelled',
        v_old_number, v_old_number, NULLIF(TRIM(p_reason), '')
    );

    COMMIT;
    SET p_success = TRUE;
    SET p_message = 'Appointment cancelled successfully';
END$$

DELIMITER ;
