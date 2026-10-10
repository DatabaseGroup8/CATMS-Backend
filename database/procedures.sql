-- CATMS FINAL procedures, fresh install on MySQL 8.0.16+.
-- Run after functions.sql; keep Django stored-procedure signatures unchanged.
-- No retired procedures: CreateConsultationWithDetails, GenerateInvoice,
-- AddPrescriptionWithItems, AddTreatment, AddClaim, ProcessInsuranceClaim.
-- AuthenticateUser omitted (unnecessary and unsafe hash equality; Django verifies passwords).
DELIMITER $$

CREATE PROCEDURE AddTimeSlot(
    IN p_doctor_id INT, IN p_branch_id INT, IN p_available_date DATE,
    IN p_start_time TIME, IN p_end_time TIME,
    OUT p_time_slot_id INT, OUT p_error_message VARCHAR(255), OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_employee_id INT DEFAULT NULL;
    DECLARE v_count INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message=MESSAGE_TEXT;
        ROLLBACK; SET p_time_slot_id=NULL; SET p_success=FALSE;
    END;
    SET p_time_slot_id=NULL; SET p_error_message=NULL; SET p_success=FALSE;
    IF p_doctor_id IS NULL OR p_branch_id IS NULL OR p_available_date IS NULL
       OR p_start_time IS NULL OR p_end_time IS NULL OR p_end_time<=p_start_time
       OR p_available_date<CURDATE() THEN
        SET p_error_message='Invalid doctor, branch, date or time range';
        LEAVE proc_label;
    END IF;
    START TRANSACTION;
    -- Lock employee for concurrent slot creation by this doctor.
    SELECT d.employee_id INTO v_employee_id
      FROM Doctor d JOIN Employee e ON e.employee_id=d.employee_id
      WHERE d.doctor_id=p_doctor_id AND e.branch_id=p_branch_id
        AND e.role='Doctor' AND e.status='Active' FOR UPDATE;
    IF v_employee_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Doctor not active at selected branch';
    END IF;
    SELECT COUNT(*) INTO v_count FROM Time_Slot ts
      WHERE ts.doctor_id=p_doctor_id AND ts.available_date=p_available_date
        AND ts.start_time<p_end_time AND ts.end_time>p_start_time;
    IF v_count>0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Overlapping doctor time slot';
    END IF;
    INSERT INTO Time_Slot(doctor_id,branch_id,available_date,is_booked,start_time,end_time)
    VALUES(p_doctor_id,p_branch_id,p_available_date,FALSE,p_start_time,p_end_time);
    SET p_time_slot_id=LAST_INSERT_ID();
    COMMIT; SET p_success=TRUE; SET p_error_message='Time slot added successfully';
END$$

CREATE PROCEDURE GetStaffByBranch(
    IN p_branch_name VARCHAR(100), IN p_role VARCHAR(50),
    IN p_active_only BOOLEAN, IN p_limit INT, IN p_offset INT
)
BEGIN
    SELECT e.employee_id,e.branch_id,e.role,e.salary,e.joined_date,e.status,
           u.user_id,u.full_name,u.NIC,u.gender,u.DOB,u.email,u.contact_no,
           b.branch_name,a.address_line_1,a.address_line_2,a.city,a.province,a.postal_code
    FROM Employee e JOIN `User` u ON u.user_id=e.user_id
    JOIN Branch b ON b.branch_id=e.branch_id
    LEFT JOIN Address a ON a.address_id=u.address_id
    WHERE b.branch_name=TRIM(p_branch_name)
      AND (p_role IS NULL OR p_role='' OR e.role=p_role)
      AND (COALESCE(p_active_only,FALSE)=FALSE OR e.status='Active')
    ORDER BY u.full_name
    LIMIT p_limit OFFSET p_offset;
END$$

CREATE PROCEDURE UpdateStaffSalary(
    IN p_employee_id INT, IN p_new_salary DECIMAL(10,2),
    OUT p_error_message VARCHAR(255), OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN ROLLBACK; SET p_success=FALSE; SET p_error_message='Salary update failed'; END;
    SET p_success=FALSE; SET p_error_message=NULL;
    IF p_new_salary IS NULL OR p_new_salary<0 THEN
        SET p_error_message='Invalid salary'; LEAVE proc_label;
    END IF;
    START TRANSACTION;
    SELECT COUNT(*) INTO v_count FROM Employee WHERE employee_id=p_employee_id;
    IF v_count=0 THEN ROLLBACK; SET p_error_message='Employee not found'; LEAVE proc_label; END IF;
    UPDATE Employee SET salary=p_new_salary WHERE employee_id=p_employee_id;
    COMMIT; SET p_success=TRUE; SET p_error_message='Salary updated';
END$$

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
END$$

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
END$$

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

END proc_label$$

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

END proc_label$$

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

CREATE PROCEDURE RegisterPatient(
    IN p_registered_branch_id INT,
    IN p_full_name VARCHAR(100),
    IN p_contact_no VARCHAR(20),
    IN p_DOB DATE,
    IN p_NIC VARCHAR(20),
    IN p_gender VARCHAR(20),

    OUT p_patient_id INT,
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
BEGIN
    DECLARE v_nic VARCHAR(20);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;

        SET p_patient_id = NULL;
        SET p_success = FALSE;
        SET p_message = 'Database error during patient registration.';
    END;

    SET p_patient_id = NULL;
    SET p_success = FALSE;
    SET p_message = NULL;

    SET v_nic = NULLIF(TRIM(p_NIC), '');

    -- Step 1: Validate patient information
    IF p_full_name IS NULL
       OR TRIM(p_full_name) = '' THEN

        SET p_message = 'Full name is required.';

    ELSEIF p_DOB IS NULL THEN

        SET p_message = 'Date of birth is required.';

    ELSEIF p_DOB > CURDATE() THEN

        SET p_message = 'Date of birth cannot be in the future.';

    ELSEIF NOT EXISTS (
        SELECT 1 FROM Branch
        WHERE branch_id = p_registered_branch_id
    ) THEN

        SET p_message = 'Invalid branch.';

    ELSEIF v_nic IS NOT NULL AND EXISTS (
        SELECT 1 FROM Patient
        WHERE NIC = v_nic
    ) THEN

        SET p_message = 'Patient with this NIC already exists.';

    ELSE

        START TRANSACTION;

        -- Step 2: Insert patient and calculate age
        INSERT INTO Patient (
            registered_branch_id,
            full_name,
            contact_no,
            DOB,
            age,
            NIC,
            gender
        )
        VALUES (
            p_registered_branch_id,
            TRIM(p_full_name),
            NULLIF(TRIM(p_contact_no), ''),
            p_DOB,
            CalculateAge(p_DOB),
            v_nic,
            NULLIF(TRIM(p_gender), '')
        );

        -- Step 3: Retrieve new patient ID
        SET p_patient_id = LAST_INSERT_ID();

        COMMIT;

        SET p_success = TRUE;
        SET p_message = 'Patient registered successfully.';

    END IF;

END$$

-- One transaction per operation. MySQL 8.0, database selected in caller.
-- The old CreateConsultationWithDetails/GenerateInvoice procedures must not be called
-- by your frontend after switching to this workflow.

CREATE PROCEDURE MarkAppointmentCompleted(
    IN p_appointment_id INT, IN p_doctor_employee_id INT,
    OUT p_success BOOLEAN, OUT p_message VARCHAR(255)
)
proc: BEGIN
    DECLARE v_doctor_employee_id INT DEFAULT NULL;
    DECLARE v_status VARCHAR(50) DEFAULT NULL;
    DECLARE v_branch_id INT DEFAULT NULL;
    DECLARE v_active INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message = MESSAGE_TEXT;
        ROLLBACK; SET p_success = FALSE;
    END;
    SET p_success = FALSE; SET p_message = NULL;
    START TRANSACTION;
    SELECT d.employee_id, a.status, ts.branch_id
      INTO v_doctor_employee_id, v_status, v_branch_id
    FROM Appointment a JOIN Time_Slot ts ON a.time_slot_id=ts.time_slot_id
    JOIN Doctor d ON d.doctor_id=ts.doctor_id
    WHERE a.appointment_id=p_appointment_id FOR UPDATE;
    SELECT COUNT(*) INTO v_active FROM Employee e
      WHERE e.employee_id=p_doctor_employee_id AND e.role='Doctor'
        AND e.status='Active' AND e.branch_id=v_branch_id;
    IF v_doctor_employee_id IS NULL OR v_doctor_employee_id <> p_doctor_employee_id
       OR v_active <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Doctor not authorized for appointment';
    END IF;
    IF v_status <> 'Scheduled' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Only Scheduled appointments can be completed';
    END IF;
    UPDATE Appointment SET status='Completed', updated_at=CURDATE()
    WHERE appointment_id=p_appointment_id;
    COMMIT;
    SET p_success=TRUE; SET p_message='Appointment completed';
END$$

CREATE PROCEDURE FinalizeConsultationBill(
    IN p_appointment_id INT,
    IN p_employee_id INT,
    IN p_chief_complaint TEXT,
    IN p_symptoms TEXT,
    IN p_diagnosis TEXT,
    IN p_medications JSON,
    IN p_treatments JSON,
    OUT p_medical_record_id INT,
    OUT p_invoice_id INT,
    OUT p_subtotal DECIMAL(12,2),
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
proc: BEGIN
    DECLARE v_status VARCHAR(50) DEFAULT NULL;
    DECLARE v_branch INT DEFAULT NULL;
    DECLARE v_authorized INT DEFAULT 0;
    DECLARE v_existing INT DEFAULT 0;
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_n INT DEFAULT 0;
    DECLARE v_med_id INT DEFAULT NULL;
    DECLARE v_t_code INT DEFAULT NULL;
    DECLARE v_quantity INT;
    DECLARE v_price DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_eligible BOOLEAN DEFAULT NULL;
    DECLARE v_dosage VARCHAR(50);
    DECLARE v_frequency VARCHAR(50);
    DECLARE v_duration VARCHAR(50);
    DECLARE v_instructions TEXT;
    DECLARE v_raw VARCHAR(100);
    DECLARE v_med_total DECIMAL(12,2);
    DECLARE v_treat_total DECIMAL(12,2);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message=MESSAGE_TEXT;
        ROLLBACK;
        SET p_success=FALSE;
        SET p_medical_record_id=NULL;
        SET p_invoice_id=NULL;
        SET p_subtotal=NULL;
    END;
    SET p_medical_record_id=NULL; SET p_invoice_id=NULL;
    SET p_subtotal=NULL; SET p_success=FALSE; SET p_message=NULL;
    IF p_medications IS NULL OR JSON_TYPE(p_medications)<>'ARRAY'
       OR p_treatments IS NULL OR JSON_TYPE(p_treatments)<>'ARRAY' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Items must be JSON arrays';
    END IF;
    IF JSON_LENGTH(p_medications)+JSON_LENGTH(p_treatments)=0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='At least one billable item is required';
    END IF;
    IF TRIM(COALESCE(p_chief_complaint,''))=''
       OR TRIM(COALESCE(p_diagnosis,''))='' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Chief complaint and diagnosis required';
    END IF;
    IF JSON_LENGTH(p_medications)>100 OR JSON_LENGTH(p_treatments)>100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Too many consultation items';
    END IF;
    START TRANSACTION;
    -- Serializes duplicate finalization for the same appointment.
    SELECT a.status, ts.branch_id INTO v_status, v_branch
      FROM Appointment a JOIN Time_Slot ts ON a.time_slot_id=ts.time_slot_id
      WHERE a.appointment_id=p_appointment_id FOR UPDATE;
    IF v_status IS NULL OR v_status<>'Completed' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Appointment must be Completed';
    END IF;
    SELECT COUNT(*) INTO v_authorized FROM Employee e
      WHERE e.employee_id=p_employee_id AND e.role='Receptionist'
        AND e.status='Active' AND e.branch_id=v_branch;
    IF v_authorized<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unauthorized receptionist/branch';
    END IF;
    SELECT (SELECT COUNT(*) FROM consultation_record WHERE appointment_id=p_appointment_id)
         + (SELECT COUNT(*) FROM Invoice WHERE appointment_id=p_appointment_id)
      INTO v_existing;
    IF v_existing>0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Consultation or invoice already finalized';
    END IF;
    INSERT INTO Medical_record (chief_complaint,symptoms,diagnosis)
        VALUES (p_chief_complaint,p_symptoms,p_diagnosis);
    SET p_medical_record_id=LAST_INSERT_ID();
    -- Medicines. NULL/invalid items are rejected before any partial commit.
    SET v_n=JSON_LENGTH(p_medications); SET v_i=0;
    WHILE v_i<v_n DO
        IF JSON_TYPE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,']')))<>'OBJECT' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid medication item';
        END IF;
        SET v_raw=JSON_UNQUOTE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,'].medication_id')));
        IF v_raw IS NULL OR v_raw NOT REGEXP '^[1-9][0-9]*$'
           OR CHAR_LENGTH(v_raw)>10 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid medication ID';
        END IF;
        SET v_med_id=CAST(v_raw AS UNSIGNED);
        SET v_raw=JSON_UNQUOTE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,'].quantity')));
        IF v_raw IS NULL OR v_raw NOT REGEXP '^[1-9][0-9]*$' OR CHAR_LENGTH(v_raw)>5 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid medication quantity';
        END IF;
        SET v_quantity=CAST(v_raw AS UNSIGNED);
        IF v_quantity>10000 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Medication quantity too large';
        END IF;
        SET v_dosage=JSON_UNQUOTE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,'].dosage')));
        SET v_frequency=JSON_UNQUOTE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,'].frequency')));
        SET v_duration=JSON_UNQUOTE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,'].duration_days')));
        SET v_instructions=JSON_UNQUOTE(JSON_EXTRACT(p_medications, CONCAT('$[',v_i,'].instructions')));
        IF v_dosage IS NULL OR TRIM(v_dosage)='' OR v_frequency IS NULL OR TRIM(v_frequency)=''
           OR v_duration IS NULL OR v_duration NOT REGEXP '^[1-9][0-9]*$'
           OR CHAR_LENGTH(v_duration)>5 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Incomplete dosage/frequency/duration';
        END IF;
        SET v_price=NULL;
        SELECT m.price INTO v_price FROM Medication m WHERE m.medication_id=v_med_id;
        IF v_price IS NULL OR v_price<0 OR v_price*v_quantity>99999999.99 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Medication missing or price invalid';
        END IF;
        INSERT INTO Prescription
            (medical_record_id,medication_id,dosage,frequency,duration_days,instructions,quantity,unit_price)
            VALUES(p_medical_record_id,v_med_id,v_dosage,v_frequency,v_duration,v_instructions,v_quantity,v_price);
        SET v_i=v_i+1;
    END WHILE;
    -- Treatments. Each array entry is one billable occurrence.
    SET v_n=JSON_LENGTH(p_treatments); SET v_i=0;
    WHILE v_i<v_n DO
        SET v_raw=JSON_UNQUOTE(JSON_EXTRACT(p_treatments,CONCAT('$[',v_i,'].treatment_service_code')));
        IF v_raw IS NULL OR v_raw NOT REGEXP '^[1-9][0-9]*$' OR CHAR_LENGTH(v_raw)>10 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid treatment code';
        END IF;
        SET v_t_code=CAST(v_raw AS UNSIGNED);
        SET v_price=NULL; SET v_eligible=NULL;
        SELECT tc.base_price, tc.insurance_eligible INTO v_price,v_eligible
          FROM Treatment_Catalogue tc WHERE tc.treatment_service_code=v_t_code;
        IF v_price IS NULL OR v_price<0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Treatment missing or price invalid';
        END IF;
        INSERT INTO Treatment (medical_record_id,treatment_service_code,unit_price,insurance_eligible)
            VALUES(p_medical_record_id,v_t_code,v_price,COALESCE(v_eligible,FALSE));
        SET v_i=v_i+1;
    END WHILE;
    SET v_med_total=CalculateMedicationTotal(p_medical_record_id);
    SET v_treat_total=CalculateTreatmentTotal(p_medical_record_id);
    SET p_subtotal=v_med_total+v_treat_total;
    IF p_subtotal<=0 OR p_subtotal>99999999.99 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invoice subtotal invalid';
    END IF;
    INSERT INTO Invoice (appointment_id,sub_total,insurance_claimed_amount,created_at)
        VALUES (p_appointment_id,p_subtotal,0.00,CURDATE());
    SET p_invoice_id=LAST_INSERT_ID();
    INSERT INTO consultation_record (appointment_id,medical_record_id,invoice_id)
        VALUES (p_appointment_id,p_medical_record_id,p_invoice_id);
    COMMIT;
    SET p_success=TRUE; SET p_message='Consultation and invoice finalized';
END$$

-- Replaces old RecordPayment and old claim processing routes/procedures.
-- All routines use InnoDB transactional tables and a consistent invoice row lock.

CREATE PROCEDURE ApplyInvoiceInsurance(
    IN p_invoice_id INT, IN p_insurance_id INT, IN p_employee_id INT,
    OUT p_claim_amount DECIMAL(10,2), OUT p_success BOOLEAN, OUT p_message VARCHAR(255)
)
proc: BEGIN
    DECLARE v_patient_id INT DEFAULT NULL;
    DECLARE v_branch_id INT DEFAULT NULL;
    DECLARE v_service_date DATE DEFAULT NULL;
    DECLARE v_subtotal DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_auth INT DEFAULT 0;
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_copay DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_eligible DECIMAL(12,2) DEFAULT 0.00;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message = MESSAGE_TEXT;
        ROLLBACK; SET p_success=FALSE; SET p_claim_amount=NULL;
    END;
    SET p_success=FALSE; SET p_claim_amount=NULL; SET p_message=NULL;
    START TRANSACTION;
    SELECT a.patient_id, ts.branch_id, ts.available_date, i.sub_total
      INTO v_patient_id, v_branch_id, v_service_date, v_subtotal
      FROM Invoice i JOIN Appointment a ON a.appointment_id=i.appointment_id
      JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
      WHERE i.Invoice_id=p_invoice_id AND a.status='Completed' FOR UPDATE;
    IF v_patient_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completed invoice not found';
    END IF;
    SELECT COUNT(*) INTO v_auth FROM Employee
      WHERE employee_id=p_employee_id AND branch_id=v_branch_id
        AND role='Receptionist' AND status='Active';
    IF v_auth<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unauthorized receptionist/branch';
    END IF;
    IF v_subtotal IS NULL OR v_subtotal<=0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invoice amount invalid';
    END IF;
    SELECT COUNT(*) INTO v_count FROM Claims WHERE invoice_id=p_invoice_id;
    IF v_count>0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Insurance already applied to invoice';
    END IF;
    SELECT COUNT(*) INTO v_count FROM Payment WHERE Invoice_id=p_invoice_id;
    IF v_count>0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Apply insurance before patient payments';
    END IF;
    SELECT ip.copayment_percentage INTO v_copay
      FROM Insurance ins JOIN Insurance_Packages ip
        ON ip.insurance_package_id=ins.insurance_package_id
      WHERE ins.Insurance_id=p_insurance_id AND ins.patient_id=v_patient_id
        AND ins.status='Active'
        AND ins.started_date<=v_service_date
        AND (ins.end_date IS NULL OR ins.end_date>=v_service_date)
        AND (ip.started_date IS NULL OR ip.started_date<=v_service_date)
      LIMIT 1;
    IF v_copay IS NULL OR v_copay<0 OR v_copay>100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='No eligible active insurance for patient';
    END IF;
    SET v_eligible=CalculateEligibleTreatmentTotal(p_invoice_id);
    IF v_eligible<=0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='No insurance-eligible treatments';
    END IF;
    SET p_claim_amount=CaculateInsuranceCoverage(LEAST(v_subtotal,v_eligible),v_copay);
    IF p_claim_amount IS NULL OR p_claim_amount<=0 OR p_claim_amount>v_subtotal THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Calculated insurance amount invalid';
    END IF;
    INSERT INTO Claims(insurance_id,invoice_id,issued_date,claim_amount,
                       approved_amount,insurance_paid_amount,claim_status)
    VALUES (p_insurance_id,p_invoice_id,CURDATE(),p_claim_amount,NULL,0.00,'Submitted');
    UPDATE Invoice SET insurance_claimed_amount=p_claim_amount WHERE Invoice_id=p_invoice_id;
    COMMIT;
    SET p_success=TRUE; SET p_message='Insurance claim submitted (provisional)';
END$$

CREATE PROCEDURE RecordPayment(
    IN p_invoice_id INT,
    IN p_employee_id INT,
    IN p_payment_amount DECIMAL(10,2),
    IN p_payment_method VARCHAR(20),
    IN p_request_key VARCHAR(36),
    OUT p_payment_id INT,
    OUT p_success BOOLEAN,
    OUT p_message VARCHAR(255)
)
proc: BEGIN
    DECLARE v_patient_id INT DEFAULT NULL;
    DECLARE v_branch INT DEFAULT NULL;
    DECLARE v_status VARCHAR(50) DEFAULT NULL;
    DECLARE v_auth INT DEFAULT 0;
    DECLARE v_remaining DECIMAL(12,2) DEFAULT NULL;
    DECLARE v_existing_id INT DEFAULT NULL;
    DECLARE v_existing_invoice INT;
    DECLARE v_existing_amount DECIMAL(10,2);
    DECLARE v_existing_method VARCHAR(20);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message=MESSAGE_TEXT;
        ROLLBACK; SET p_payment_id=NULL; SET p_success=FALSE;
    END;
    SET p_payment_id=NULL; SET p_success=FALSE; SET p_message=NULL;
    IF p_payment_amount IS NULL OR p_payment_amount<=0
        OR p_payment_method IS NULL OR TRIM(p_payment_method)=''
        OR p_request_key IS NULL OR CHAR_LENGTH(p_request_key)<>36 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid payment amount/method/request key';
    END IF;
    START TRANSACTION;
    SELECT a.patient_id,ts.branch_id,a.status
      INTO v_patient_id,v_branch,v_status
      FROM Invoice i JOIN Appointment a ON a.appointment_id=i.appointment_id
      JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
      WHERE i.Invoice_id=p_invoice_id FOR UPDATE;
    IF v_patient_id IS NULL OR v_status<>'Completed' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Completed invoice not found';
    END IF;
    SELECT COUNT(*) INTO v_auth FROM Employee e
    WHERE e.employee_id=p_employee_id AND e.role='Receptionist'
      AND e.status='Active' AND e.branch_id=v_branch;
    IF v_auth<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unauthorized receptionist/branch';
    END IF;
    -- Safe payment retry: same request_key, same amount/method/invoice -> same payment ID.
    SELECT payment_id,Invoice_id,payment_amount,payment_method
      INTO v_existing_id,v_existing_invoice,v_existing_amount,v_existing_method
      FROM Payment WHERE request_key=p_request_key LIMIT 1;
    IF v_existing_id IS NOT NULL THEN
        IF v_existing_invoice<>p_invoice_id OR v_existing_amount<>p_payment_amount
           OR v_existing_method<>p_payment_method THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Payment request key reused for different details';
        END IF;
        SET p_payment_id=v_existing_id;
        COMMIT;
        SET p_success=TRUE; SET p_message='Previous payment returned (idempotent retry)';
        LEAVE proc;
    END IF;
    SET v_remaining=CalculateOutstandingBalance(p_invoice_id);
    IF v_remaining IS NULL OR v_remaining<=0 OR p_payment_amount>v_remaining THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Payment exceeds patient outstanding balance';
    END IF;
    INSERT INTO Payment (Invoice_id,patient_id,payment_method,status,payment_date,
                         payment_amount,request_key)
    VALUES (p_invoice_id,v_patient_id,p_payment_method,'Completed',CURDATE(),
            p_payment_amount,p_request_key);
    SET p_payment_id=LAST_INSERT_ID();
    COMMIT;
    SET p_success=TRUE; SET p_message='Payment recorded successfully';
END$$

CREATE PROCEDURE ResolveInsuranceClaim(
    IN p_invoice_id INT, IN p_manager_employee_id INT,
    IN p_approved_amount DECIMAL(10,2),
    OUT p_success BOOLEAN, OUT p_message VARCHAR(255)
)
proc: BEGIN
    DECLARE v_branch INT DEFAULT NULL;
    DECLARE v_auth INT DEFAULT 0;
    DECLARE v_claimed DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_paid DECIMAL(10,2) DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message=MESSAGE_TEXT;
        ROLLBACK; SET p_success=FALSE;
    END;
    SET p_success=FALSE; SET p_message=NULL;
    START TRANSACTION;
    SELECT ts.branch_id INTO v_branch
      FROM Invoice i JOIN Appointment a ON a.appointment_id=i.appointment_id
      JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
      WHERE i.Invoice_id=p_invoice_id FOR UPDATE;
    IF v_branch IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invoice not found';
    END IF;
    SELECT COUNT(*) INTO v_auth FROM Employee e
      WHERE e.employee_id=p_manager_employee_id AND e.branch_id=v_branch
        AND e.role='Manager' AND e.status='Active';
    IF v_auth<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Manager unauthorized';
    END IF;
    SELECT c.claim_amount,c.claim_status,c.insurance_paid_amount
      INTO v_claimed,v_status,v_paid
      FROM Claims c WHERE c.invoice_id=p_invoice_id FOR UPDATE;
    IF v_status IS NULL OR v_status<>'Submitted' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Claim not pending';
    END IF;
    IF p_approved_amount IS NULL OR p_approved_amount<0 OR p_approved_amount>v_claimed THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid approved amount';
    END IF;
    UPDATE Claims SET approved_amount=p_approved_amount,
       claim_status=CASE WHEN p_approved_amount=0 THEN 'Rejected'
                         WHEN p_approved_amount<v_claimed THEN 'PartiallyApproved'
                         ELSE 'Approved' END
     WHERE invoice_id=p_invoice_id;
    -- Claim allocation is provisionally applied when Submitted. Once adjudicated,
    -- use the approved share (if rejected, the patient owes the difference).
    UPDATE Invoice SET insurance_claimed_amount=p_approved_amount
      WHERE Invoice_id=p_invoice_id;
    COMMIT;
    SET p_success=TRUE; SET p_message='Insurance claim decision recorded';
END$$

-- Optional demonstration of an insurer reimbursement. Does NOT insert patient Payment.

CREATE PROCEDURE RecordInsuranceSettlement(
    IN p_invoice_id INT, IN p_manager_employee_id INT,
    IN p_amount DECIMAL(10,2),
    OUT p_success BOOLEAN, OUT p_message VARCHAR(255)
)
proc: BEGIN
    DECLARE v_branch INT DEFAULT NULL;
    DECLARE v_auth INT DEFAULT 0;
    DECLARE v_approved DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_paid DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_status VARCHAR(20) DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message=MESSAGE_TEXT;
        ROLLBACK; SET p_success=FALSE;
    END;
    SET p_success=FALSE; SET p_message=NULL;
    IF p_amount IS NULL OR p_amount<=0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Settlement amount must be positive';
    END IF;
    START TRANSACTION;
    SELECT ts.branch_id INTO v_branch
      FROM Invoice i JOIN Appointment a ON a.appointment_id=i.appointment_id
      JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
      WHERE i.Invoice_id=p_invoice_id FOR UPDATE;
    IF v_branch IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invoice not found';
    END IF;
    SELECT COUNT(*) INTO v_auth FROM Employee
      WHERE employee_id=p_manager_employee_id AND branch_id=v_branch
        AND role='Manager' AND status='Active';
    IF v_auth<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Manager unauthorized';
    END IF;
    SELECT approved_amount,insurance_paid_amount,claim_status
      INTO v_approved,v_paid,v_status FROM Claims WHERE invoice_id=p_invoice_id FOR UPDATE;
    IF v_approved IS NULL OR v_approved<=0
       OR v_status NOT IN ('Approved','PartiallyApproved','PartiallyPaid') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Insurance claim not approved';
    END IF;
    IF v_paid+p_amount>v_approved THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Settlement exceeds approved amount';
    END IF;
    UPDATE Claims SET insurance_paid_amount=v_paid+p_amount,
      claim_status=CASE WHEN v_paid+p_amount=v_approved
                        THEN 'Paid' ELSE 'PartiallyPaid' END
      WHERE invoice_id=p_invoice_id;
    COMMIT;
    SET p_success=TRUE; SET p_message='Insurer settlement recorded';
END$$

-- Replacement for your existing AddMedication: adds the required price input.

CREATE PROCEDURE AddMedication(
    IN p_generic_name VARCHAR(100),
    IN p_manufacturer VARCHAR(100),
    IN p_form VARCHAR(50),
    IN p_contraindications VARCHAR(255),
    IN p_side_effects VARCHAR(255),
    IN p_price DECIMAL(10,2),
    OUT p_medication_id INT,
    OUT p_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc: BEGIN
    DECLARE v_exists INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_message = MESSAGE_TEXT;
        ROLLBACK; SET p_medication_id=NULL; SET p_success=FALSE;
    END;
    SET p_medication_id=NULL; SET p_message=NULL; SET p_success=FALSE;
    IF p_generic_name IS NULL OR TRIM(p_generic_name)='' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Generic name is required';
    END IF;
    IF p_price IS NULL OR p_price<0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Medication price is required';
    END IF;
    START TRANSACTION;
    SELECT COUNT(*) INTO v_exists FROM Medication
     WHERE generic_name=p_generic_name
       AND manufacturer <=> p_manufacturer AND form <=> p_form;
    IF v_exists>0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Medication already exists';
    END IF;
    INSERT INTO Medication (generic_name,manufacturer,form,contraindications,side_effects,price)
    VALUES(p_generic_name,p_manufacturer,p_form,p_contraindications,p_side_effects,p_price);
    SET p_medication_id=LAST_INSERT_ID();
    COMMIT;
    SET p_success=TRUE; SET p_message='Medication added successfully';
END$$

DELIMITER ;
