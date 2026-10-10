-- CATMS full fresh schema | MySQL 8.0.16+ / Aiven MySQL
-- FRESH EMPTY DATABASE ONLY. Do not run in an existing populated schema.
-- Select the intended database first (e.g. USE catms_dev_v2;).
-- Exactly 26 tables. This is the final schema (NO follow-up ALTER/migrations).

SET NAMES utf8mb4;

-- 1. Address Table
CREATE TABLE Address (
    address_id INT PRIMARY KEY AUTO_INCREMENT,
    address_line_1 VARCHAR(150),
    address_line_2 VARCHAR(150),
    city VARCHAR(50),
    province VARCHAR(50),
    postal_code VARCHAR(10)
) ENGINE=InnoDB;

-- 2. User Table
CREATE TABLE `User` (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    address_id INT,
    full_name VARCHAR(100),
    NIC VARCHAR(20),
    gender VARCHAR(10),
    DOB DATE,
    email VARCHAR(150) NOT NULL UNIQUE,
    contact_no VARCHAR(15),
    Password_hash VARCHAR(255),
    FOREIGN KEY (address_id) REFERENCES Address(address_id)
) ENGINE=InnoDB;

-- 3. Branch Table
CREATE TABLE Branch (
    branch_id INT PRIMARY KEY AUTO_INCREMENT,
    branch_name VARCHAR(100),
    district VARCHAR(50),
    contact_id INT,
    address_id INT,
    FOREIGN KEY (address_id) REFERENCES Address(address_id)
) ENGINE=InnoDB;

-- 4. Employee Table
CREATE TABLE Employee (
    employee_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    branch_id INT,
    role VARCHAR(50),
    salary DECIMAL(10,2),
    joined_date DATE,
    status VARCHAR(20) DEFAULT 'Active',
    FOREIGN KEY (user_id) REFERENCES `User`(user_id),
    FOREIGN KEY (branch_id) REFERENCES Branch(branch_id)
) ENGINE=InnoDB;

-- 5. Doctor Table
CREATE TABLE Doctor (
    doctor_id INT PRIMARY KEY AUTO_INCREMENT,
    employee_id INT,
    room_no VARCHAR(10),
    medical_licence_number VARCHAR(50),
    FOREIGN KEY (employee_id) REFERENCES Employee(employee_id)
) ENGINE=InnoDB;

-- 6. Patient Table
CREATE TABLE Patient (
    patient_id INT AUTO_INCREMENT PRIMARY KEY,
    registered_branch_id INT,
    contact_no VARCHAR(20),
    full_name VARCHAR(100),
    NIC VARCHAR(20) UNIQUE,
    gender VARCHAR(20),
    DOB DATE,
    age SMALLINT UNSIGNED,
    FOREIGN KEY (registered_branch_id) REFERENCES Branch(branch_id)
) ENGINE=InnoDB;



-- 7. Condition category Table
CREATE TABLE Condition_category( 
    condition_category_id INT AUTO_INCREMENT PRIMARY KEY, 
    category_name VARCHAR(100)
) ENGINE=InnoDB;

-- 8. Conditions
CREATE TABLE Conditions( 
    condition_id INT AUTO_INCREMENT PRIMARY KEY, 
    condition_category_id INT, 
    condition_name VARCHAR(100), 
    description TEXT, 
    FOREIGN KEY (condition_category_id) REFERENCES Condition_category(condition_category_id)
) ENGINE=InnoDB; 

-- 9. Patient_condition 
CREATE TABLE Patient_condition( 
    patient_condition_id INT AUTO_INCREMENT PRIMARY KEY, 
    patient_id INT,
    condition_id INT,
    diagnosed_date DATE , 
    is_chronic BOOLEAN, 
    current_status VARCHAR(30), 
    FOREIGN KEY (patient_id) REFERENCES Patient(patient_id), 
    FOREIGN KEY (condition_id) REFERENCES Conditions(condition_id)
) ENGINE=InnoDB;

-- 10. Specialization Table
CREATE TABLE Specialization (
    specialization_id INT AUTO_INCREMENT PRIMARY KEY,
    specialization_name VARCHAR(100),
    description TEXT
) ENGINE=InnoDB;

-- 11. Doctor_Specialization Table
CREATE TABLE Doctor_Specialization (
    specialization_id INT,
    doctor_id INT,
    PRIMARY KEY (specialization_id, doctor_id),
    FOREIGN KEY (specialization_id) REFERENCES Specialization(specialization_id),
    FOREIGN KEY (doctor_id) REFERENCES Doctor(doctor_id)
) ENGINE=InnoDB;

-- 12. Time_Slot Table
CREATE TABLE Time_Slot (
    time_slot_id INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id INT NOT NULL,
    branch_id INT NOT NULL,
    available_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    available BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (doctor_id) REFERENCES Doctor(doctor_id),
    FOREIGN KEY (branch_id) REFERENCES Branch(branch_id),
    CONSTRAINT chk_slot_time CHECK (end_time > start_time),
    INDEX idx_slot_doctor_date (doctor_id, available_date)
) ENGINE=InnoDB;


-- 13. Appointment Table
CREATE TABLE Appointment (
    appointment_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT,
    time_slot_id INT,
    appointment_number INT NOT NULL,
    type VARCHAR(50),
    status VARCHAR(50),
    notes TEXT,
    updated_at DATE,
    created_at DATE,
    FOREIGN KEY (patient_id) REFERENCES Patient(patient_id),
    FOREIGN KEY (time_slot_id) REFERENCES Time_Slot(time_slot_id),
    UNIQUE (time_slot_id, appointment_number)
) ENGINE=InnoDB;

-- 14. Medical Record Table
CREATE TABLE Medical_record (
    medical_record_id INT AUTO_INCREMENT PRIMARY KEY,
    chief_complaint TEXT,
    symptoms TEXT,
    diagnosis TEXT
) ENGINE=InnoDB;

-- 15. Medication Table
CREATE TABLE Medication (
    medication_id INT AUTO_INCREMENT PRIMARY KEY,
    generic_name VARCHAR(100),
    manufacturer VARCHAR(100),
    form VARCHAR(50),
    contraindications VARCHAR(255),
    side_effects VARCHAR(255),
    price DECIMAL(10,2) NOT NULL,
    CONSTRAINT chk_medication_price CHECK (price >= 0)
) ENGINE=InnoDB;

-- 16. Prescription Table
CREATE TABLE Prescription (
    prescription_id INT AUTO_INCREMENT PRIMARY KEY,
    medical_record_id INT,
    medication_id INT,
    dosage VARCHAR(50),
    frequency VARCHAR(50),
    duration_days VARCHAR(50),
    instructions TEXT,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    CONSTRAINT chk_prescription_quantity CHECK (quantity > 0),
    CONSTRAINT chk_prescription_price CHECK (unit_price >= 0),
    FOREIGN KEY (medical_record_id) REFERENCES Medical_record(medical_record_id),
    FOREIGN KEY (medication_id) REFERENCES Medication(medication_id)
) ENGINE=InnoDB;

-- 17. Treatment Category Table
CREATE TABLE Treatment_Category (
    treatment_category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100),
    description TEXT
) ENGINE=InnoDB;

-- 18. Treatment Catalogue Table
CREATE TABLE Treatment_Catalogue (
    treatment_service_code INT AUTO_INCREMENT PRIMARY KEY,
    treatment_category_id INT,
    treatment_name VARCHAR(100),
    base_price DECIMAL(10, 2),
    duration VARCHAR(50),
    updated_date DATE,
    insurance_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_catalogue_price CHECK (base_price IS NULL OR base_price >= 0),
    FOREIGN KEY (treatment_category_id) REFERENCES Treatment_Category(treatment_category_id)
) ENGINE=InnoDB;

-- 19. Treatment Table
CREATE TABLE Treatment (
    treatment_id INT AUTO_INCREMENT PRIMARY KEY,
    medical_record_id INT,
    treatment_service_code INT,
    unit_price DECIMAL(10,2) NOT NULL,
    insurance_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_treatment_price CHECK (unit_price >= 0),
    FOREIGN KEY (medical_record_id) REFERENCES Medical_record(medical_record_id),
    FOREIGN KEY (treatment_service_code) REFERENCES Treatment_Catalogue(treatment_service_code)
) ENGINE=InnoDB;


-- 20. Invoice Table
Create TABLE Invoice (
    Invoice_id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL UNIQUE,
    sub_total DECIMAL(10,2) NOT NULL,
    insurance_claimed_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_at DATE DEFAULT (CURRENT_DATE),
    CONSTRAINT chk_invoice_money CHECK (sub_total >= 0 AND insurance_claimed_amount >= 0 AND insurance_claimed_amount <= sub_total),
    FOREIGN KEY(appointment_id) REFERENCES Appointment(appointment_id)
) ENGINE=InnoDB;

-- 21. Payment Table
Create TABLE Payment (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    Invoice_id INT,
    patient_id INT,
    payment_method VARCHAR(20),
    status VARCHAR(20),
    payment_date DATE,
    payment_amount DECIMAL(10,2) NOT NULL,
    request_key VARCHAR(36) NOT NULL UNIQUE,
    CONSTRAINT chk_payment_amount CHECK (payment_amount > 0),
    FOREIGN KEY(Invoice_id) REFERENCES Invoice(Invoice_id),
    FOREIGN KEY(patient_id) REFERENCES Patient(patient_id)
) ENGINE=InnoDB;

-- 22. Insurance_Packages Table
Create Table Insurance_Packages (
    insurance_package_id INT AUTO_INCREMENT PRIMARY KEY,
    package_name VARCHAR(50),
    annual_name VARCHAR(50),
    copayment_percentage DECIMAL(10,2),
    updated_date DATE,
    started_date DATE,
    CONSTRAINT chk_insurance_copay CHECK (copayment_percentage IS NULL OR (copayment_percentage BETWEEN 0 AND 100))
) ENGINE=InnoDB;

-- 23. Insurance Table
Create Table Insurance (
    Insurance_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT,
    insurance_package_id INT,
    updated_date DATE,
    status VARCHAR(50),
    started_date DATE,
    end_date DATE,
    FOREIGN KEY(patient_id) REFERENCES Patient(patient_id) ,
    FOREIGN KEY(insurance_package_id) REFERENCES Insurance_Packages(insurance_package_id) 
) ENGINE=InnoDB;

-- 24.Claims Table
Create Table Claims (
    insurance_id INT,
    invoice_id INT,
    issued_date DATE,
    claim_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    approved_amount DECIMAL(10,2) DEFAULT NULL,
    insurance_paid_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    claim_status VARCHAR(20) NOT NULL DEFAULT 'Submitted',
    UNIQUE (invoice_id),
    CONSTRAINT chk_claim_amounts CHECK (claim_amount >= 0 AND insurance_paid_amount >= 0 AND (approved_amount IS NULL OR (approved_amount >= 0 AND approved_amount <= claim_amount))),
    PRIMARY KEY(insurance_id,invoice_id),
    FOREIGN KEY(invoice_id) REFERENCES Invoice(invoice_id),
    FOREIGN KEY(insurance_id) REFERENCES Insurance(insurance_id)
) ENGINE=InnoDB;

-- 25.Consultation Record Table
CREATE TABLE consultation_record(
    consultation_rec_id INT PRIMARY KEY AUTO_INCREMENT,
    appointment_id INT NOT NULL UNIQUE,
    medical_record_id INT ,
    invoice_id INT,
    FOREIGN KEY (medical_record_id) REFERENCES Medical_record(medical_record_id) ,
    FOREIGN KEY (invoice_id) REFERENCES Invoice(invoice_id) ,
    FOREIGN KEY (appointment_id) REFERENCES Appointment(appointment_id) 
) ENGINE=InnoDB;

-- 26.Manager Table
CREATE TABLE Manager(
    branch_id INT,
    employee_id INT,
    PRIMARY KEY(branch_id),
    FOREIGN KEY (branch_id) REFERENCES Branch(branch_id) ,
    FOREIGN KEY (employee_id) REFERENCES Employee(employee_id)
) ENGINE=InnoDB;
