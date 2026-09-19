
-- Procedure: AddMedication

CREATE PROCEDURE AddMedication(
    --IN parameters receice the raw data from backend
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
    DECLARE v_duplicate_count INT DEFAULT 0;
    
    -- 1. The Error Handler: If anything crashes, undo the changes and report back
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

-- Procedure: CreateConsultationWithDetails

CREATE PROCEDURE CreateConsultationWithDetails(
    IN p_appointment_id INT,
    IN p_chief_complaint VARCHAR(255),
    IN p_symptoms TEXT,
    IN p_diagnoses TEXT,
    
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
    INSERT INTO Medical_record (chief_complaint, symptoms, diagnoses)
    VALUES (p_chief_complaint, p_symptoms, p_diagnoses);
    
    SET v_medical_record_id = LAST_INSERT_ID();

    -- 6. Insert Consultation Record
    INSERT INTO Consultation_record (appointment_id, medical_record_id) 
    VALUES (p_appointment_id, v_medical_record_id);
    
    SET p_consultation_id = LAST_INSERT_ID();

    -- 7. Update Appointment Status
    UPDATE Appointment SET status = 'Completed' WHERE appointment_id = p_appointment_id;

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

