CREATE DATABASE IF NOT EXISTS `saffron_bank` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

USE `saffron_bank`;

SET NAMES utf8mb4;

DROP TABLE IF EXISTS `loan_applications`;

DROP TABLE IF EXISTS `support_tickets`;

DROP TABLE IF EXISTS `transactions`;

DROP TABLE IF EXISTS `cards`;

DROP TABLE IF EXISTS `accounts`;

DROP TABLE IF EXISTS `international_customers`;

DROP TABLE IF EXISTS `kyc_records`;

DROP TABLE IF EXISTS `customers`;

DROP TABLE IF EXISTS `branches`;

CREATE TABLE `branches` (
    `branch_code` VARCHAR(6) NOT NULL,
    `ifsc` VARCHAR(11) NOT NULL,
    `branch_nm` VARCHAR(80) NOT NULL,
    `addr` VARCHAR(160) NOT NULL,
    `city` VARCHAR(40) NOT NULL,
    `state` VARCHAR(40) NOT NULL,
    `pincode` VARCHAR(6) NOT NULL,
    `branch_phone` VARCHAR(20) NOT NULL,
    `branch_email` VARCHAR(80) NOT NULL,
    `region` VARCHAR(16) NOT NULL,
    `opened_on` DATE NOT NULL,
    PRIMARY KEY (`branch_code`),
    UNIQUE (`ifsc`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `customers` (
    `customer_id` VARCHAR(16) NOT NULL,
    `cust_nm` VARCHAR(80) NOT NULL,
    `gender` VARCHAR(8),
    `dob_dt` DATE NOT NULL,
    `mob_no` VARCHAR(20) NOT NULL,
    `emailid` VARCHAR(80),
    `addr_line1` VARCHAR(120) NOT NULL,
    `addr_line2` VARCHAR(120),
    `city` VARCHAR(40) NOT NULL,
    `state` VARCHAR(40) NOT NULL,
    `pincode` VARCHAR(6) NOT NULL,
    `pita_nm` VARCHAR(80),
    `alt_mob` VARCHAR(20),
    `occupation` VARCHAR(40),
    `segment` VARCHAR(20) NOT NULL,
    `risk_cat` VARCHAR(8) NOT NULL,
    `home_branch` VARCHAR(6) NOT NULL,
    `customer_since` DATE NOT NULL,
    `preferred_lang` VARCHAR(12),
    `last_login_ts` DATETIME,
    PRIMARY KEY (`customer_id`),
    FOREIGN KEY (`home_branch`) REFERENCES `branches` (`branch_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `kyc_records` (
    `kyc_id` VARCHAR(16) NOT NULL,
    `customer_id` VARCHAR(16) NOT NULL,
    `pan_no` VARCHAR(10),
    `aadhaar_no` VARCHAR(16),
    `ovd_type` VARCHAR(30),
    `kyc_status` VARCHAR(12) NOT NULL,
    `kyc_mode` VARCHAR(16) NOT NULL,
    `verified_on` DATE,
    `verified_by` VARCHAR(12),
    `next_review_dt` DATE,
    `kyc_meta` JSON,
    PRIMARY KEY (`kyc_id`),
    FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `international_customers` (
    `customer_id` VARCHAR(16) NOT NULL,
    `ssn` VARCHAR(11) NOT NULL,
    `us_addr` VARCHAR(120) NOT NULL,
    `us_city` VARCHAR(40) NOT NULL,
    `us_state` VARCHAR(2) NOT NULL,
    `us_zip` VARCHAR(10) NOT NULL,
    `us_phone` VARCHAR(24),
    `residency_status` VARCHAR(20) NOT NULL,
    `fatca_flag` VARCHAR(1) NOT NULL,
    `tax_form` VARCHAR(8) NOT NULL,
    `tin_country` VARCHAR(2) NOT NULL,
    `fatca_reported_on` DATE,
    PRIMARY KEY (`customer_id`),
    FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `accounts` (
    `account_no` VARCHAR(16) NOT NULL,
    `customer_id` VARCHAR(16) NOT NULL,
    `branch_code` VARCHAR(6) NOT NULL,
    `ifsc` VARCHAR(11) NOT NULL,
    `acct_type` VARCHAR(12) NOT NULL,
    `curr_bal` DECIMAL(15,2) NOT NULL,
    `open_dt` DATE NOT NULL,
    `acct_status` VARCHAR(10) NOT NULL,
    `nominee_nm` VARCHAR(80),
    `nominee_rel` VARCHAR(20),
    `od_limit_inr` DECIMAL(15,2),
    `int_rate_pct` DECIMAL(5,2) NOT NULL,
    `extra_info` TEXT,
    `last_txn_dt` DATE,
    PRIMARY KEY (`account_no`),
    FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`),
    FOREIGN KEY (`branch_code`) REFERENCES `branches` (`branch_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `cards` (
    `CARD_REF` VARCHAR(16) NOT NULL,
    `CUSTOMER_ID` VARCHAR(16) NOT NULL,
    `LINKED_ACCT` VARCHAR(16),
    `CARD_NO` VARCHAR(19) NOT NULL,
    `CARD_NETWORK` VARCHAR(12) NOT NULL,
    `CARD_TYPE` VARCHAR(8) NOT NULL,
    `CARD_VARIANT` VARCHAR(12) NOT NULL,
    `NAME_ON_CARD` VARCHAR(26) NOT NULL,
    `EXP_MM` INT NOT NULL,
    `EXP_YYYY` INT NOT NULL,
    `CREDIT_LIMIT` DECIMAL(15,2),
    `OUTSTANDING_AMT` DECIMAL(15,2),
    `CARD_STATUS` VARCHAR(12) NOT NULL,
    `ISSUED_ON` DATE NOT NULL,
    PRIMARY KEY (`CARD_REF`),
    FOREIGN KEY (`CUSTOMER_ID`) REFERENCES `customers` (`customer_id`),
    FOREIGN KEY (`LINKED_ACCT`) REFERENCES `accounts` (`account_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `transactions` (
    `txn_id` VARCHAR(16) NOT NULL,
    `account_no` VARCHAR(16) NOT NULL,
    `txn_ts` DATETIME NOT NULL,
    `amount_inr` DECIMAL(15,2) NOT NULL,
    `dr_cr` VARCHAR(2) NOT NULL,
    `channel` VARCHAR(12) NOT NULL,
    `counterparty` VARCHAR(80),
    `narration` TEXT NOT NULL,
    `ref_no` VARCHAR(24),
    `rrn` VARCHAR(12),
    `bal_after` DECIMAL(15,2),
    `txn_status` VARCHAR(10) NOT NULL,
    PRIMARY KEY (`txn_id`),
    FOREIGN KEY (`account_no`) REFERENCES `accounts` (`account_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `support_tickets` (
    `ticket_id` VARCHAR(16) NOT NULL,
    `customer_id` VARCHAR(16),
    `created_ts` DATETIME NOT NULL,
    `channel` VARCHAR(16) NOT NULL,
    `category` VARCHAR(32) NOT NULL,
    `priority` VARCHAR(8) NOT NULL,
    `ticket_text` TEXT NOT NULL,
    `notes` TEXT,
    `status` VARCHAR(12) NOT NULL,
    `resolved_ts` DATETIME,
    `assigned_to` VARCHAR(20),
    PRIMARY KEY (`ticket_id`),
    FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `loan_applications` (
    `app_id` VARCHAR(16) NOT NULL,
    `customer_id` VARCHAR(16) NOT NULL,
    `loan_type` VARCHAR(16) NOT NULL,
    `applied_on` DATE NOT NULL,
    `amt_requested_inr` DECIMAL(15,2) NOT NULL,
    `tenure_mths` INT NOT NULL,
    `declared_income_inr` DECIMAL(15,2),
    `employer_nm` VARCHAR(60),
    `emp_type` VARCHAR(16) NOT NULL,
    `credit_score` INT,
    `decision` VARCHAR(12) NOT NULL,
    `sanctioned_amt_inr` DECIMAL(15,2),
    `roi_pct` DECIMAL(5,2),
    `col_7` VARCHAR(12),
    `remarks` TEXT,
    PRIMARY KEY (`app_id`),
    FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
