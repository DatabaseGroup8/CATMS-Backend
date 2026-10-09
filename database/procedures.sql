DELIMITER //
-- Procedure: AddMedication

CREATE PROCEDURE AddMedication(
    --IN parameters receive the raw data from backend
    --MySQL automatically takes values from the backend and drop into IN parameters
    IN p_generic_name VARCHAR(100),
    IN p_manufacturer VARCHAR(100),
    IN p_form VARCHAR(50),
    IN p_contraindications VARCHAR(255),
    IN p_side_effects VARCHAR(255),
    
    --OUT parameters send the final result back to the backend
    OUT p_medication_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_duplicate_count INT DEFAULT 0; --to keep track of how many identical rows already exist in the database
    
    -- 1. The Error Handler: If anything crashes, undo the changes and report back(SQL version of try....catch)
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_medication_id = NULL;
    
    -- 3. Start Transaction
    START TRANSACTION;
    
    -- 4. Validation: Prevent empty names
    IF p_generic_name IS NULL OR TRIM(p_generic_name) = '' THEN
        SET p_error_message = 'Generic name is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 5. Validation: Check for exact duplicates in the Medication table
    SELECT COUNT(*) INTO v_duplicate_count
    FROM Medication
    WHERE generic_name = p_generic_name 
    AND manufacturer = p_manufacturer
    AND form = p_form;
    
    IF v_duplicate_count > 0 THEN
        SET p_error_message = 'This medication already exists in the system';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 6. Insert the Data
    INSERT INTO Medication (
        generic_name, 
        manufacturer, 
        form, 
        contraindications, 
        side_effects
    ) VALUES (
        p_generic_name,
        p_manufacturer,
        p_form,
        p_contraindications,
        p_side_effects
    );
    
    -- 7. Success! Grab the auto-generated INT ID
    SET p_medication_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Medication added successfully';
    
    COMMIT;
END //
--........................................................................................................................

-- Procedure: CreateConsultationWithDetails
DELIMITER //

CREATE PROCEDURE CreateConsultationWithDetails(
    IN p_appointment_id INT,
    IN p_chief_complaint VARCHAR(255),
    IN p_symptoms TEXT,
    IN p_diagnosis TEXT,
    
    -- JSON Arrays sent from the frontend
    IN p_treatments JSON,       
    IN p_prescriptions JSON,    
    
    OUT p_consultation_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_medical_record_id INT;
    DECLARE v_appointment_exists INT DEFAULT 0;
    
    -- JSON loop variables
    DECLARE v_idx INT DEFAULT 0;
    DECLARE v_array_length INT DEFAULT 0;
    
    -- Treatment extraction variables
    DECLARE v_treatment_code INT;
    
    -- Prescription extraction variables
    DECLARE v_med_id INT;
    DECLARE v_dosage VARCHAR(255);
    DECLARE v_freq VARCHAR(255);
    DECLARE v_days INT;
    DECLARE v_instr VARCHAR(255);

    -- 1. The Error Handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_consultation_id = NULL;

    -- 3. Start Transaction
    START TRANSACTION;

    -- 4. Validate Appointment
    SELECT COUNT(*) INTO v_appointment_exists 
    FROM Appointment 
    WHERE appointment_id = p_appointment_id AND status = 'Scheduled';
    
    IF v_appointment_exists = 0 THEN
        SET p_error_message = 'Valid Scheduled Appointment not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 5. Insert Medical Record
    INSERT INTO Medical_record (chief_complaint, symptoms, diagnosis)
    VALUES (p_chief_complaint, p_symptoms, p_diagnosis);
    
    SET v_medical_record_id = LAST_INSERT_ID();

    -- 6. Insert Consultation Record
    INSERT INTO Consultation_record (appointment_id, medical_record_id) 
    VALUES (p_appointment_id, v_medical_record_id);
    
    SET p_consultation_id = LAST_INSERT_ID();

    -- 7. Update Appointment Status
    UPDATE Appointment SET status = 'Completed' WHERE appointment_id = p_appointment_id;

    INSERT INTO Invoice (appointment_id, sub_total, insurance_claimed_amount)
    VALUES (p_appointment_id, 0.00, 0.00);

    -- 8. Parse and Insert Treatments
    IF p_treatments IS NOT NULL AND JSON_LENGTH(p_treatments) > 0 THEN
        SET v_array_length = JSON_LENGTH(p_treatments);
        SET v_idx = 0;
        
        WHILE v_idx < v_array_length DO
            -- Dynamically extract the treatment code based on the loop index
            SET v_treatment_code = JSON_UNQUOTE(JSON_EXTRACT(p_treatments, CONCAT('$[', v_idx, '].treatment_service_code')));
            
            INSERT INTO Treatment (medical_record_id, treatment_service_code)
            VALUES (v_medical_record_id, v_treatment_code);
            
            SET v_idx = v_idx + 1;
        END WHILE;
    END IF;

    -- 9. Parse and Insert Prescriptions
    IF p_prescriptions IS NOT NULL AND JSON_LENGTH(p_prescriptions) > 0 THEN
        SET v_array_length = JSON_LENGTH(p_prescriptions);
        SET v_idx = 0;
        
        WHILE v_idx < v_array_length DO
            -- Extract all prescription fields for the current array object
            SET v_med_id = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].medication_id')));
            SET v_dosage = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].dosage')));
            SET v_freq = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].frequency')));
            SET v_days = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].duration_days')));
            SET v_instr = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].instructions')));
            
            INSERT INTO Prescription (medical_record_id, medication_id, dosage, frequency, duration_days, instructions)
            VALUES (v_medical_record_id, v_med_id, v_dosage, v_freq, v_days, v_instr);
            
            SET v_idx = v_idx + 1;
        END WHILE;
    END IF;

    -- 10. Commit the Transaction
    SET p_success = TRUE;
    SET p_error_message = 'Consultation and details saved successfully';

    COMMIT;
END //
DELIMITER;
--...............................................................................................................................

-- Procedure: AddPrescriptionWithItems
DELIMITER //

CREATE PROCEDURE AddPrescriptionWithItems(
    IN p_medical_record_id INT,
    IN p_prescription_items JSON,
    
    OUT p_items_added INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_record_exists INT DEFAULT 0;
    DECLARE v_idx INT DEFAULT 0;
    DECLARE v_array_length INT DEFAULT 0;
    
    -- Extraction variables
    DECLARE v_med_id INT;
    DECLARE v_dosage VARCHAR(50);
    DECLARE v_freq VARCHAR(50);
    DECLARE v_days VARCHAR(50);
    DECLARE v_instr VARCHAR(255);

    -- 1. Error Handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_items_added = 0;

    -- 3. Start Transaction
    START TRANSACTION;

    -- 4. Validate Medical Record
    SELECT COUNT(*) INTO v_record_exists 
    FROM Medical_record 
    WHERE medical_record_id = p_medical_record_id;
    
    IF v_record_exists = 0 THEN
        SET p_error_message = 'Medical record not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 5. Validate JSON Array
    IF p_prescription_items IS NULL OR JSON_LENGTH(p_prescription_items) = 0 THEN
        SET p_error_message = 'Prescription items array cannot be empty';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 6. Parse and Insert Loop
    SET v_array_length = JSON_LENGTH(p_prescription_items);
    
    WHILE v_idx < v_array_length DO
        SET v_med_id = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].medication_id')));
        SET v_dosage = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].dosage')));
        SET v_freq = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].frequency')));
        SET v_days = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].duration_days')));
        SET v_instr = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].instructions')));
        
        INSERT INTO Prescription (
            medical_record_id, medication_id, dosage, frequency, duration_days, instructions
        ) VALUES (
            p_medical_record_id, v_med_id, v_dosage, v_freq, v_days, v_instr
        );
        
        SET p_items_added = p_items_added + 1;
        SET v_idx = v_idx + 1;
    END WHILE;

    -- 7. Success Output
    SET p_success = TRUE;
    SET p_error_message = 'Prescriptions added successfully';

    COMMIT;
END //
DELIMITER;
--......................................................................................................................................
--Procedure: AddPatientCondition
DELIMITER //

CREATE PROCEDURE AddPatientCondition(
    IN p_patient_id INT,
    IN p_condition_id INT,
    IN p_diagnosed_date DATE,
    IN p_is_chronic BOOLEAN,
    IN p_current_status VARCHAR(30),
    
    OUT p_patient_condition_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_patient_exists INT DEFAULT 0;
    DECLARE v_condition_exists INT DEFAULT 0;
    DECLARE v_duplicate_count INT DEFAULT 0;

    -- 1. The Error Handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_patient_condition_id = NULL;

    -- 3. Start Transaction
    START TRANSACTION;

    -- 4. Foreign Key Validation: Patient
    SELECT COUNT(*) INTO v_patient_exists 
    FROM Patient 
    WHERE patient_id = p_patient_id;
    
    IF v_patient_exists = 0 THEN
        SET p_error_message = 'Patient not found in the system';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 5. Foreign Key Validation: Condition
    SELECT COUNT(*) INTO v_condition_exists 
    FROM Conditions 
    WHERE condition_id = p_condition_id;
    
    IF v_condition_exists = 0 THEN
        SET p_error_message = 'Condition not found in the medical dictionary';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 6. Logical Validation: Prevent Duplicates
    SELECT COUNT(*) INTO v_duplicate_count FROM Patient_Condition 
    WHERE patient_id = p_patient_id 
    AND condition_id = p_condition_id
    AND diagnosed_date = p_diagnosed_date;
    
    IF v_duplicate_count > 0 THEN
        SET p_error_message = 'This patient already has this condition recorded for today';
        ROLLBACK; LEAVE proc_label;
    END IF;

    -- 7. Insert the Record
    INSERT INTO Patient_Condition (
        patient_id, 
        condition_id, 
        diagnosed_date, 
        is_chronic, 
        current_status
    ) VALUES (
        p_patient_id, 
        p_condition_id, 
        p_diagnosed_date, 
        p_is_chronic, 
        p_current_status
    );

    -- 8. Success Output
    SET p_patient_condition_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Patient condition recorded successfully';

    COMMIT;
END//
DELIMITER;
--..............................................................................................................
--Procedure: AddTreatment
DELIMITER //

CREATE PROCEDURE AddTreatment(
    IN p_medical_record_id INT,
    IN p_treatment_service_code INT,
    
    OUT p_treatment_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_record_exists INT DEFAULT 0;
    DECLARE v_service_exists INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_treatment_id = NULL;

    START TRANSACTION;

    SELECT COUNT(*) INTO v_record_exists 
    FROM Medical_record 
    WHERE medical_record_id = p_medical_record_id;
    
    IF v_record_exists = 0 THEN
        SET p_error_message = 'Medical record not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    SELECT COUNT(*) INTO v_service_exists 
    FROM Treatment_catalogue 
    WHERE treatment_service_code = p_treatment_service_code;
    
    IF v_service_exists = 0 THEN
        SET p_error_message = 'Invalid treatment service code';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    INSERT INTO Treatment (medical_record_id, treatment_service_code)
    VALUES (p_medical_record_id, p_treatment_service_code);

    SET p_treatment_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Treatment added successfully';

    COMMIT;
END //
DELIMITER;

--.................................................................................................................
-- Procedure: Record Payment
DELIMITER //

DROP PROCEDURE IF EXISTS `RecordPayment`$$
CREATE PROCEDURE `RecordPayment`(
    IN p_invoice_id INT,
    IN p_user_id INT,
    IN p_appointment_id INT,
    IN p_payment_amount DECIMAL(10,2),
    IN p_payment_method VARCHAR(100),
    OUT p_payment_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_outstanding DECIMAL(10,2);
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    
    START TRANSACTION;
    
    -- Check balance using the custom function
    SET v_outstanding = CalculateOutstandingBalance(p_invoice_id);
    
    IF p_payment_amount <= 0 THEN
        SET p_error_message = 'Payment amount must be greater than zero';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    IF p_payment_amount > v_outstanding THEN
        SET p_error_message = 'Payment exceeds outstanding balance';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- Insert the payment record[cite: 1, 2]
    INSERT INTO Payment (Invoice_id, patient_id, payment_method, status, payment_date, payment_amount)
    VALUES (p_invoice_id, p_user_id, p_payment_method, 'Completed', CURDATE(), p_payment_amount);
    
    SET p_payment_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Payment recorded successfully';
    
    COMMIT;
END proc_label//
DELIMITER;

--...................................................................................................................................
-- Procedure: Process Insurance Claim
DELIMITER //

DROP PROCEDURE IF EXISTS `ProcessInsuranceClaim`$$
CREATE PROCEDURE `ProcessInsuranceClaim`(
    IN p_invoice_id INT,
    IN p_insurance_id INT,
    IN p_claim_amount DECIMAL(10,2),
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_invoice_exists INT DEFAULT 0;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    START TRANSACTION;
    
    SELECT COUNT(*) INTO v_invoice_exists FROM Invoice WHERE Invoice_id = p_invoice_id;
    
    IF v_invoice_exists = 0 THEN
        SET p_error_message = 'Invoice not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    INSERT INTO Claims (insurance_id, invoice_id, issued_date)
    VALUES (p_insurance_id, p_invoice_id, CURDATE());
    
    UPDATE Invoice 
    SET insurance_claimed_amount = insurance_claimed_amount + p_claim_amount
    WHERE Invoice_id = p_invoice_id;
    
    SET p_success = TRUE;
    SET p_error_message = 'Claim processed successfully';
    
    COMMIT;
END proc_label//
DELIMITER ;
--...................................................................................................................................
-- Procedure: Add timeslots to timslot table

DELIMITER //
DROP PROCEDURE IF EXISTS `AddTimeSlot`//

CREATE PROCEDURE `AddTimeSlot`(
    IN p_doctor_id INT,
    IN p_branch_id INT,
    IN p_available_date DATE,
    IN p_start_time TIME,
    IN p_end_time TIME,
   
    OUT p_time_slot_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    -- ALL DECLARE STATEMENTS MUST COME FIRST
    DECLARE v_doctor_exists INT DEFAULT 0;
    DECLARE v_branch_exists INT DEFAULT 0;
   
    -- Error handler (must be declared AFTER variables but BEFORE any SET/SELECT)
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
   
    -- NOW executable statements can start
    -- Initialize outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_time_slot_id = NULL;
   
    -- Start transaction
    START TRANSACTION;
   
    -- Validation: Check if doctor exists
    SELECT COUNT(*) INTO v_doctor_exists
    FROM doctor
    WHERE doctor_id = p_doctor_id;
   
    IF v_doctor_exists = 0 THEN
        SET p_error_message = 'Doctor not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Validation: Check if branch exists
    SELECT COUNT(*) INTO v_branch_exists
    FROM Branch
    WHERE branch_id = p_branch_id;
    
   
    IF v_branch_exists = 0 THEN
        SET p_error_message = 'Branch not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Validation: Check required fields
    IF p_available_date IS NULL THEN
        SET p_error_message = 'Available date is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    IF p_start_time IS NULL THEN
        SET p_error_message = 'Start time is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    IF p_end_time IS NULL THEN
        SET p_error_message = 'End time is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Validation: Check end_time > start_time
    IF p_end_time <= p_start_time THEN
        SET p_error_message = 'End time must be after start time';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Insert time slot
    INSERT INTO time_slot (
        doctor_id, branch_id, available_date, 
        is_booked, start_time, end_time
    ) VALUES (
        p_doctor_id, p_branch_id, p_available_date, 
        FALSE, p_start_time, p_end_time
    );
   
    -- Success
    SET p_time_slot_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Time slot added successfully';
   
    COMMIT;
END proc_label//
DELIMITER ;

--...................................................................................................................................
-- Procedure: CreateTimeSlot
-- DELIMITER //
-- CREATE PROCEDURE `CreateTimeSlot`(
--     IN p_doctor_id INT,
--     IN p_branch_id INT,
--     IN p_available_date DATE,
--     IN p_start_time TIME,
--     IN p_end_time TIME,
--     OUT p_time_slot_id CHAR(36),
--     OUT p_error_message VARCHAR(255),
--     OUT p_success BOOLEAN
-- )
-- proc_label: BEGIN
--     -- ...existing code from AddTimeSlot...
--     DECLARE v_time_slot_id INT;
--     DECLARE v_doctor_exists INT DEFAULT 0;
--     DECLARE v_branch_exists INT DEFAULT 0;
--     --If an SQL error happens while executing this block, run the error-handling code and then exit the block
--     DECLARE EXIT HANDLER FOR SQLEXCEPTION
--     BEGIN
--         GET DIAGNOSTICS CONDITION 1
--             p_error_message = MESSAGE_TEXT;
--         ROLLBACK;
--         SET p_success = FALSE;
--     END;
--     SET p_success = FALSE;
--     SET p_error_message = NULL;
--     SET p_time_slot_id = NULL;
--     START TRANSACTION;
--     SELECT COUNT(*) INTO v_doctor_exists FROM doctor WHERE doctor_id = p_doctor_id;
--     IF v_doctor_exists = 0 THEN
--         SET p_error_message = 'Doctor not found';
--         ROLLBACK;
--         LEAVE proc_label;
--     END IF;
--     SELECT COUNT(*) INTO v_branch_exists FROM branch WHERE branch_id = p_branch_id AND is_active = TRUE;
--     IF v_branch_exists = 0 THEN
--         SET p_error_message = 'Branch not found or inactive';
--         ROLLBACK;
--         LEAVE proc_label;
--     END IF;
--     IF p_available_date IS NULL THEN
--         SET p_error_message = 'Available date is required';
--         ROLLBACK;
--         LEAVE proc_label;
--     END IF;
--     IF p_start_time IS NULL THEN
--         SET p_error_message = 'Start time is required';
--         ROLLBACK;
--         LEAVE proc_label;
--     END IF;
--     IF p_end_time IS NULL THEN
--         SET p_error_message = 'End time is required';
--         ROLLBACK;
--         LEAVE proc_label;
--     END IF;
--     IF p_end_time <= p_start_time THEN
--         SET p_error_message = 'End time must be after start time';
--         ROLLBACK;
--         LEAVE proc_label;
--     END IF;
--     SET v_time_slot_id = UUID();
--     INSERT INTO time_slot (
--         time_slot_id, doctor_id, branch_id, available_date, 
--         is_booked, start_time, end_time
--     ) VALUES (
--         v_time_slot_id, p_doctor_id, p_branch_id, p_available_date, 
--         FALSE, p_start_time, p_end_time
--     );
--     SET p_time_slot_id = v_time_slot_id;
--     SET p_success = TRUE;
--     SET p_error_message = 'Time slot added successfully';
--     COMMIT;
-- END proc_label//
-- DELIMITER;


--...................................................................................................................................
-- Procedure: BookAppointment
DELIMITER //

DROP PROCEDURE IF EXISTS `BookAppointment`//

CREATE PROCEDURE `BookAppointment`(
    -- INPUT PARAMETERS: Data passed in from the Django backend
    IN p_patient_id INT,
    IN p_time_slot_id INT,
    IN p_type VARCHAR(50),       -- e.g., 'Consultation', 'Follow-up'
    IN p_notes TEXT,
    
    -- OUTPUT PARAMETERS: Data sent back to the Django backend
    OUT p_appointment_id INT,    -- The primary key of the new appointment
    OUT p_appointment_number INT,-- The calculated queue/token number
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    -- Internal variables used during processing
    DECLARE v_patient_exists INT DEFAULT 0;
    DECLARE v_slot_date DATE;
    DECLARE v_next_number INT DEFAULT 1;
    
    -- ERROR HANDLER: If any SQL error occurs, rollback all changes and exit safely
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    -- Initialize output variables
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_appointment_id = NULL;
    SET p_appointment_number = NULL;
    
    -- Start the transaction to ensure atomicity (all or nothing)
    START TRANSACTION;
    
    -- 1. Validate Patient: Ensure the patient exists before attempting to book
    SELECT COUNT(*) INTO v_patient_exists 
    FROM Patient 
    WHERE patient_id = p_patient_id;
    
    IF v_patient_exists = 0 THEN
        SET p_error_message = 'Patient not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 2. Validate Slot & Lock for Concurrency: 
    -- 'FOR UPDATE' locks this specific daily time slot row for this transaction.
    -- This prevents two receptionists from calculating the MAX() token at the exact same millisecond.
    SELECT available_date INTO v_slot_date
    FROM Time_Slot 
    WHERE time_slot_id = p_time_slot_id
    FOR UPDATE;
    
    IF v_slot_date IS NULL THEN
        SET p_error_message = 'Time slot not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- Prevent booking appointments for past dates
    IF v_slot_date < CURDATE() THEN
        SET p_error_message = 'Cannot book an appointment in the past';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 3. Calculate Queue Number: Find the highest token for this specific daily slot.
    -- COALESCE handles the very first patient by treating NULL as 0, then adds 1.
    SELECT COALESCE(MAX(appointment_number), 0) + 1 INTO v_next_number 
    FROM Appointment 
    WHERE time_slot_id = p_time_slot_id;
    
    -- 4. Create the Appointment: Save the record with the calculated token and current dates.
    INSERT INTO Appointment (
        time_slot_id, 
        patient_id, 
        appointment_number, 
        type, 
        status, 
        notes, 
        created_at, 
        updated_at
    )
    VALUES (
        p_time_slot_id, 
        p_patient_id, 
        v_next_number, 
        p_type, 
        'Scheduled', 
        p_notes, 
        CURDATE(), -- Automatically stamps today's date for created_at
        CURDATE()  -- Automatically stamps today's date for updated_at
    );
    
    -- Verify the INSERT was successful
    IF ROW_COUNT() != 1 THEN
        SET p_error_message = 'Failed to create appointment record';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 5. Return Success Data: Pass the new IDs back to Django
    SET p_appointment_id = LAST_INSERT_ID();  -- Grabs the auto-incremented primary key
    SET p_appointment_number = v_next_number; -- Grabs the calculated queue token
    SET p_success = TRUE;
    SET p_error_message = 'Appointment booked successfully';
    
    -- Save all changes permanently
    COMMIT;
END //

DELIMITER ;

--...................................................................................................................
DELIMITER //

    --Procedure Generate Invoice--
DROP PROCEDURE IF EXISTS GenerateInvoice //

CREATE PROCEDURE GenerateInvoice(
    IN p_appointment_id INT,
    OUT p_invoice_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_appointment_exists INT DEFAULT 0;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    SET p_error_message = NULL;
    
    START TRANSACTION;
    
    -- Verify the appointment exists and is marked as Completed
    SELECT COUNT(*) INTO v_appointment_exists 
    FROM Appointment 
    WHERE appointment_id = p_appointment_id AND status = 'Completed';
    
    IF v_appointment_exists = 0 THEN
        SET p_error_message = 'Cannot generate invoice: Appointment not completed';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- Insert the blank invoice so billing triggers can populate the sub_total later
    INSERT INTO Invoice (appointment_id, sub_total, insurance_claimed_amount)
    VALUES (p_appointment_id, 0.00, 0.00);
    
    SET p_invoice_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Invoice generated successfully';
    
    COMMIT;
END //

DELIMITER ;

--...................................................................................................................................
-- Procedure: AddPatientInsurance
DELIMITER //

CREATE PROCEDURE AddPatientInsurance(
    IN p_patient_id INT,
    IN p_insurance_package_id INT,
    IN p_start_date DATE,
    IN p_end_date DATE,
    IN p_status VARCHAR(50),

    OUT p_insurance_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN

    DECLARE v_patient_exists INT DEFAULT 0;
    DECLARE v_package_exists INT DEFAULT 0;
    DECLARE v_duplicate_exists INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
        SET p_insurance_id = NULL;
    END;

    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_insurance_id = NULL;

    START TRANSACTION;

    -- Check patient
    SELECT COUNT(*)
    INTO v_patient_exists
    FROM Patient
    WHERE patient_id = p_patient_id;

    IF v_patient_exists = 0 THEN
        SET p_error_message = 'Patient not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Check insurance package
    SELECT COUNT(*)
    INTO v_package_exists
    FROM Insurance_Packages
    WHERE insurance_package_id = p_insurance_package_id;

    IF v_package_exists = 0 THEN
        SET p_error_message = 'Insurance package not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Check required dates
    IF p_start_date IS NULL THEN
        SET p_error_message = 'Start date is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF p_end_date IS NULL THEN
        SET p_error_message = 'End date is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Check dates
    IF p_end_date <= p_start_date THEN
        SET p_error_message = 'End date must be after start date';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Check duplicate insurance
    SELECT COUNT(*)
    INTO v_duplicate_exists
    FROM Insurance
    WHERE patient_id = p_patient_id
      AND insurance_package_id = p_insurance_package_id;

    IF v_duplicate_exists > 0 THEN
        SET p_error_message = 'Insurance package already assigned to this patient';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Insert insurance
    INSERT INTO Insurance (
        patient_id,
        insurance_package_id,
        status,
        started_date,
        end_date,
        updated_date
    )
    VALUES (
        p_patient_id,
        p_insurance_package_id,
        COALESCE(p_status, 'Pending'),
        p_start_date,
        p_end_date,
        CURRENT_DATE
    );

    -- Get AUTO_INCREMENT ID
    SET p_insurance_id = LAST_INSERT_ID();

    SET p_success = TRUE;
    SET p_error_message = 'Patient insurance added successfully';

    COMMIT;

END proc_label //

DELIMITER ;

--...................................................................................................................................
-- Procedure: AddClaim

DELIMITER //

CREATE PROCEDURE AddClaim(
    IN p_invoice_id INT,
    IN p_insurance_id INT,

    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN

    DECLARE v_invoice_exists INT DEFAULT 0;
    DECLARE v_insurance_exists INT DEFAULT 0;
    DECLARE v_claim_exists INT DEFAULT 0;

    DECLARE v_patient_id INT;
    DECLARE v_sub_total DECIMAL(10,2);
    DECLARE v_insurance_amount DECIMAL(10,2);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;

        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- Initialize
    SET p_success = FALSE;
    SET p_error_message = NULL;

    START TRANSACTION;

    -- Check invoice
    SELECT COUNT(*)
    INTO v_invoice_exists
    FROM Invoice
    WHERE Invoice_id = p_invoice_id;

    IF v_invoice_exists = 0 THEN
        SET p_error_message = 'Invoice not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Get patient and invoice amount
    SELECT
        a.patient_id,
        i.sub_total
    INTO
        v_patient_id,
        v_sub_total
    FROM Invoice i
    JOIN Appointment a
        ON i.appointment_id = a.appointment_id
    WHERE i.Invoice_id = p_invoice_id;

    -- Check insurance
    SELECT COUNT(*)
    INTO v_insurance_exists
    FROM Insurance
    WHERE Insurance_id = p_insurance_id
      AND patient_id = v_patient_id
      AND status = 'Active'
      AND started_date <= CURRENT_DATE
      AND end_date >= CURRENT_DATE;

    IF v_insurance_exists = 0 THEN
        SET p_error_message =
            'Valid active insurance not found for patient';

        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Check whether claim already exists
    SELECT COUNT(*)
    INTO v_claim_exists
    FROM Claims
    WHERE insurance_id = p_insurance_id
      AND invoice_id = p_invoice_id;

    IF v_claim_exists > 0 THEN
        SET p_error_message =
            'Claim already exists for this invoice and insurance';

        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Calculate insurance claim amount
    SET v_insurance_amount = v_sub_total;

    -- Insert claim
    INSERT INTO Claims (
        insurance_id,
        invoice_id,
        issued_date
    )
    VALUES (
        p_insurance_id,
        p_invoice_id,
        CURRENT_DATE
    );

    -- Update invoice
    UPDATE Invoice
    SET insurance_claimed_amount = v_insurance_amount
    WHERE Invoice_id = p_invoice_id;

    SET p_success = TRUE;
    SET p_error_message = 'Claim added successfully';

    COMMIT;

END proc_label //

DELIMITER ;
--...................................................................................................................................
-- Procedure: GetStaffByBranch
DELIMITER //

CREATE PROCEDURE GetStaffByBranch(
    IN p_branch_name VARCHAR(100),
    IN p_role VARCHAR(50),
    IN p_active_only BOOLEAN,
    IN p_limit INT,
    IN p_offset INT
)
proc_label: BEGIN

    DECLARE v_branch_id INT;
    DECLARE v_total_count INT DEFAULT 0;

    -- Find branch
    SELECT branch_id
    INTO v_branch_id
    FROM Branch
    WHERE branch_name = TRIM(p_branch_name)
    LIMIT 1;

    -- Check branch
    IF v_branch_id IS NULL THEN

        SELECT
            FALSE AS success,
            'Branch not found' AS error_message,
            0 AS total_count;

        LEAVE proc_label;
    END IF;

    -- Count staff
    SELECT COUNT(*)
    INTO v_total_count
    FROM Employee e
    JOIN User u
        ON e.user_id = u.user_id
    WHERE e.branch_id = v_branch_id
      AND (p_role IS NULL OR p_role = '' OR e.role = p_role)
      AND (
            p_active_only = FALSE
            OR e.status = 'Active'
          );

    -- Return staff
    SELECT
        TRUE AS success,
        'Staff retrieved successfully' AS message,
        v_total_count AS total_count,

        e.employee_id,
        e.branch_id,
        e.role,
        e.salary,
        e.joined_date,
        e.status,

        u.user_id,
        u.full_name,
        u.NIC,
        u.gender,
        u.DOB,
        u.email,
        u.contact_no,

        b.branch_name,

        a.address_line_1,
        a.address_line_2,
        a.city,
        a.province,
        a.postal_code

    FROM Employee e

    JOIN User u ON e.user_id = u.user_id

    JOIN Branch b ON e.branch_id = b.branch_id

    LEFT JOIN Address a ON u.address_id = a.address_id

    WHERE e.branch_id = v_branch_id

      AND (
            p_role IS NULL
            OR p_role = ''
            OR e.role = p_role
          )

      AND (
            p_active_only = FALSE
            OR e.status = 'Active'
          )

    ORDER BY u.full_name

    LIMIT p_limit OFFSET p_offset;

END proc_label //

DELIMITER ;

--...................................................................................................................................
-- Procedure: UpdateStaffSalary
DELIMITER //

CREATE PROCEDURE UpdateStaffSalary(
    IN p_employee_id INT,
    IN p_new_salary DECIMAL(10,2),

    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN

    DECLARE v_employee_exists INT DEFAULT 0;
    DECLARE v_current_salary DECIMAL(10,2) DEFAULT 0.00;

    -- Error handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;

        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- Initialize output values
    SET p_success = FALSE;
    SET p_error_message = NULL;

    -- Start transaction
    START TRANSACTION;

    -- Validate salary
    IF p_new_salary IS NULL THEN
        SET p_error_message = 'New salary is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    IF p_new_salary < 0 THEN
        SET p_error_message = 'Salary cannot be negative';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Check employee
    SELECT COUNT(*), COALESCE(MAX(salary), 0.00)
    INTO v_employee_exists, v_current_salary
    FROM Employee
    WHERE employee_id = p_employee_id;

    IF v_employee_exists = 0 THEN
        SET p_error_message = 'Employee does not exist';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Update salary
    UPDATE Employee
    SET salary = p_new_salary
    WHERE employee_id = p_employee_id;

    -- Success
    SET p_success = TRUE;
    SET p_error_message = 'Staff salary updated successfully';

    COMMIT;

END proc_label //

DELIMITER ;

--...................................................................................................................................
-- Procedure: DeactiveStaff

DELIMITER //

CREATE PROCEDURE DeactivateStaff(
    IN p_employee_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN

    DECLARE v_employee_exists INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;

        ROLLBACK;
        SET p_success = FALSE;
    END;

    SET p_success = FALSE;
    SET p_error_message = NULL;

    START TRANSACTION;

    -- Check whether employee exists and is currently active
    SELECT COUNT(*)
    INTO v_employee_exists
    FROM Employee
    WHERE employee_id = p_employee_id
      AND status = 'Active';

    IF v_employee_exists = 0 THEN
        SET p_error_message = 'Employee not found or already inactive';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- Deactivate employee
    UPDATE Employee
    SET status = 'Inactive'
    WHERE employee_id = p_employee_id;

    SET p_success = TRUE;
    SET p_error_message = 'Staff member deactivated successfully';

    COMMIT;

END proc_label //

DELIMITER ;

--...............................................................................................................................
--Procedure : Register Employee

DELIMITER $$

DROP PROCEDURE IF EXISTS RegisterEmployee$$

CREATE PROCEDURE RegisterEmployee(
    IN p_address_line_1 VARCHAR(150),
    IN p_address_line_2 VARCHAR(150),
    IN p_city VARCHAR(50),
    IN p_province VARCHAR(50),
    IN p_postal_code VARCHAR(10),

    IN p_full_name VARCHAR(100),
    IN p_NIC VARCHAR(20),
    IN p_gender VARCHAR(10),
    IN p_DOB DATE,
    IN p_email VARCHAR(150),
    IN p_contact_no VARCHAR(15),
    IN p_password_hash VARCHAR(255),

    IN p_branch_id INT,
    IN p_role VARCHAR(50),
    IN p_salary DECIMAL(10,2),
    IN p_joined_date DATE,

    OUT p_employee_id INT,
    OUT p_user_id INT,
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
BEGIN
    DECLARE v_address_id INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_employee_id = NULL;
        SET p_user_id = NULL;
        SET p_success = FALSE;
        SET p_message = 'Employee registration failed due to a database error.';
    END;

    SET p_employee_id = NULL;
    SET p_user_id = NULL;
    SET p_success = FALSE;
    SET p_message = NULL;

    IF NOT IsValidEmail(p_email) THEN
        SET p_message = 'Invalid email address.';

    ELSEIF p_full_name IS NULL OR TRIM(p_full_name) = '' THEN
        SET p_message = 'Full name is required.';

    ELSEIF p_password_hash IS NULL OR TRIM(p_password_hash) = '' THEN
        SET p_message = 'Password is required.';

    ELSEIF EXISTS (
        SELECT 1 FROM User WHERE email = p_email
    ) THEN
        SET p_message = 'A user with this email already exists.';

    ELSEIF p_NIC IS NOT NULL AND EXISTS (
        SELECT 1 FROM User WHERE NIC = p_NIC
    ) THEN
        SET p_message = 'A user with this NIC already exists.';

    ELSEIF NOT EXISTS (
        SELECT 1 FROM Branch WHERE branch_id = p_branch_id
    ) THEN
        SET p_message = 'Branch does not exist.';

    ELSE

        START TRANSACTION;

        -- Create address
        INSERT INTO Address (
            address_line_1,
            address_line_2,
            city,
            province,
            postal_code
        )
        VALUES (
            p_address_line_1,
            p_address_line_2,
            p_city,
            p_province,
            p_postal_code
        );

        SET v_address_id = LAST_INSERT_ID();

        -- Create user
        INSERT INTO User (
            address_id,
            full_name,
            NIC,
            gender,
            DOB,
            email,
            contact_no,
            Password_hash
        )
        VALUES (
            v_address_id,
            p_full_name,
            p_NIC,
            p_gender,
            p_DOB,
            p_email,
            p_contact_no,
            p_password_hash
        );

        SET p_user_id = LAST_INSERT_ID();

        -- Create employee
        INSERT INTO Employee (
            user_id,
            branch_id,
            role,
            salary,
            joined_date
        )
        VALUES (
            p_user_id,
            p_branch_id,
            p_role,
            p_salary,
            p_joined_date
        );

        SET p_employee_id = LAST_INSERT_ID();

        COMMIT;

        SET p_success = TRUE;
        SET p_message = 'Employee registered successfully.';

    END IF;

END$$

DELIMITER ;

--...............................................................................................................................
--Procedure : Register Doctor

DELIMITER $$

DROP PROCEDURE IF EXISTS RegisterDoctor$$

CREATE PROCEDURE RegisterDoctor(
    IN p_address_line_1 VARCHAR(150),
    IN p_address_line_2 VARCHAR(150),
    IN p_city VARCHAR(50),
    IN p_province VARCHAR(50),
    IN p_postal_code VARCHAR(10),

    IN p_full_name VARCHAR(100),
    IN p_NIC VARCHAR(20),
    IN p_gender VARCHAR(10),
    IN p_DOB DATE,
    IN p_email VARCHAR(150),
    IN p_contact_no VARCHAR(15),
    IN p_password_hash VARCHAR(255),

    IN p_branch_id INT,
    IN p_salary DECIMAL(10,2),
    IN p_joined_date DATE,

    IN p_room_no VARCHAR(10),
    IN p_medical_licence_number VARCHAR(50),

    OUT p_doctor_id INT,
    OUT p_employee_id INT,
    OUT p_user_id INT,
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
BEGIN
    DECLARE v_address_id INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_doctor_id = NULL;
        SET p_employee_id = NULL;
        SET p_user_id = NULL;
        SET p_success = FALSE;
        SET p_message = 'Doctor registration failed due to a database error.';
    END;

    SET p_doctor_id = NULL;
    SET p_employee_id = NULL;
    SET p_user_id = NULL;
    SET p_success = FALSE;
    SET p_message = NULL;

    IF NOT IsValidEmail(p_email) THEN
        SET p_message = 'Invalid email address.';

    ELSEIF p_full_name IS NULL OR TRIM(p_full_name) = '' THEN
        SET p_message = 'Full name is required.';

    ELSEIF p_password_hash IS NULL OR TRIM(p_password_hash) = '' THEN
        SET p_message = 'Password is required.';

    ELSEIF p_medical_licence_number IS NULL
           OR TRIM(p_medical_licence_number) = '' THEN
        SET p_message = 'Medical licence number is required.';

    ELSEIF EXISTS (
        SELECT 1
        FROM User
        WHERE email = p_email
    ) THEN
        SET p_message = 'A user with this email already exists.';

    ELSEIF p_NIC IS NOT NULL AND EXISTS (
        SELECT 1
        FROM User
        WHERE NIC = p_NIC
    ) THEN
        SET p_message = 'A user with this NIC already exists.';

    ELSEIF EXISTS (
        SELECT 1
        FROM Doctor
        WHERE medical_licence_number = p_medical_licence_number
    ) THEN
        SET p_message = 'A doctor with this medical licence already exists.';

    ELSEIF NOT EXISTS (
        SELECT 1
        FROM Branch
        WHERE branch_id = p_branch_id
    ) THEN
        SET p_message = 'Branch does not exist.';

    ELSE

        START TRANSACTION;

        -- Create address 
        INSERT INTO Address (
            address_line_1,
            address_line_2,
            city,
            province,
            postal_code
        )
        VALUES (
            p_address_line_1,
            p_address_line_2,
            p_city,
            p_province,
            p_postal_code
        );

        SET v_address_id = LAST_INSERT_ID();

        -- Create user 
        INSERT INTO User (
            address_id,
            full_name,
            NIC,
            gender,
            DOB,
            email,
            contact_no,
            Password_hash
        )
        VALUES (
            v_address_id,
            p_full_name,
            p_NIC,
            p_gender,
            p_DOB,
            p_email,
            p_contact_no,
            p_password_hash
        );

        SET p_user_id = LAST_INSERT_ID();

        -- Create employee
        INSERT INTO Employee (
            user_id,
            branch_id,
            role,
            salary,
            joined_date
        )
        VALUES (
            p_user_id,
            p_branch_id,
            'Doctor',
            p_salary,
            p_joined_date
        );

        SET p_employee_id = LAST_INSERT_ID();

        -- Create doctor 
        INSERT INTO Doctor (
            employee_id,
            room_no,
            medical_licence_number
        )
        VALUES (
            p_employee_id,
            p_room_no,
            p_medical_licence_number
        );

        SET p_doctor_id = LAST_INSERT_ID();

        COMMIT;

        SET p_success = TRUE;
        SET p_message = 'Doctor registered successfully.';

    END IF;

END$$

DELIMITER ;

--...............................................................................................................................
--Procedure : Register Patient

DELIMITER $$

DROP PROCEDURE IF EXISTS RegisterPatient$$

CREATE PROCEDURE RegisterPatient(
    IN p_address_line_1 VARCHAR(150),
    IN p_address_line_2 VARCHAR(150),
    IN p_city VARCHAR(50),
    IN p_province VARCHAR(50),
    IN p_postal_code VARCHAR(10),

    IN p_registered_branch_id INT,
    IN p_contact_no VARCHAR(20),
    IN p_emergency_contact_no VARCHAR(20),
    IN p_blood_group VARCHAR(5),
    IN p_full_name VARCHAR(100),
    IN p_allergies TEXT,
    IN p_chronic_conditions TEXT,
    IN p_NIC VARCHAR(20),
    IN p_gender VARCHAR(20),
    IN p_DOB DATE,
    IN p_email VARCHAR(254),

    OUT p_patient_id INT,
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
BEGIN
    DECLARE v_address_id INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_patient_id = NULL;
        SET p_success = FALSE;
        SET p_message = 'Patient registration failed due to a database error.';
    END;

    SET p_patient_id = NULL;
    SET p_success = FALSE;
    SET p_message = NULL;

    -- Validate email 
    IF NOT IsValidEmail(p_email) THEN
        SET p_message = 'Invalid email address.';
    ELSEIF p_DOB IS NULL THEN
        SET p_message = 'Date of birth is required.';
    ELSEIF p_full_name IS NULL OR TRIM(p_full_name) = '' THEN
        SET p_message = 'Full name is required.';
    ELSE
        -- Check duplicate NIC 
        IF p_NIC IS NOT NULL AND EXISTS (
            SELECT 1
            FROM Patient
            WHERE NIC = p_NIC
        ) THEN
            SET p_message = 'A patient with this NIC already exists.';
        ELSEIF EXISTS (
            SELECT 1
            FROM Patient
            WHERE email = p_email
        ) THEN
            SET p_message = 'A patient with this email already exists.';
        ELSEIF NOT EXISTS (
            SELECT 1
            FROM Branch
            WHERE branch_id = p_registered_branch_id
        ) THEN
            SET p_message = 'Registered branch does not exist.';
        ELSE

            START TRANSACTION;

            -- Create address 
            INSERT INTO Address (
                address_line_1,
                address_line_2,
                city,
                province,
                postal_code
            )
            VALUES (
                p_address_line_1,
                p_address_line_2,
                p_city,
                p_province,
                p_postal_code
            );

            SET v_address_id = LAST_INSERT_ID();

            -- Create patient 
            INSERT INTO Patient (
                address_id,
                registered_branch_id,
                contact_no,
                emergency_contact_no,
                blood_group,
                full_name,
                allergies,
                chronic_conditions,
                NIC,
                gender,
                DOB,
                email
            )
            VALUES (
                v_address_id,
                p_registered_branch_id,
                p_contact_no,
                p_emergency_contact_no,
                p_blood_group,
                p_full_name,
                p_allergies,
                p_chronic_conditions,
                p_NIC,
                p_gender,
                p_DOB,
                p_email
            );

            SET p_patient_id = LAST_INSERT_ID();

            COMMIT;

            SET p_success = TRUE;
            SET p_message = 'Patient registered successfully.';

        END IF;
    END IF;

END$$

DELIMITER ;

--...............................................................................................................................
--Procedure : Authenticate User

DELIMITER $$

DROP PROCEDURE IF EXISTS AuthenticateUser$$

CREATE PROCEDURE AuthenticateUser(
    IN p_email VARCHAR(150),
    IN p_password_hash VARCHAR(255),

    OUT p_user_id INT,
    OUT p_full_name VARCHAR(100),
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
BEGIN
    DECLARE v_stored_password_hash VARCHAR(255);

    SET p_user_id = NULL;
    SET p_full_name = NULL;
    SET p_success = FALSE;
    SET p_message = NULL;

    SELECT
        user_id,
        full_name,
        Password_hash
    INTO
        p_user_id,
        p_full_name,
        v_stored_password_hash
    FROM User
    WHERE email = p_email
    LIMIT 1;

    IF p_user_id IS NULL THEN

        SET p_success = FALSE;
        SET p_message = 'Invalid email or password.';

    ELSEIF v_stored_password_hash <> p_password_hash THEN

        SET p_user_id = NULL;
        SET p_full_name = NULL;
        SET p_success = FALSE;
        SET p_message = 'Invalid email or password.';

    ELSE

        SET p_success = TRUE;
        SET p_message = 'Authentication successful.';

    END IF;

END$$

DELIMITER ;