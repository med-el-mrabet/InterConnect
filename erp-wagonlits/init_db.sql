-- ERP WagonLits Database Schema

-- Wagons table
CREATE TABLE IF NOT EXISTS wagons (
    id SERIAL PRIMARY KEY,
    wagon_code VARCHAR(50) UNIQUE NOT NULL,
    wagon_type VARCHAR(100),
    year_built INTEGER,
    last_maintenance_date DATE,
    next_scheduled_maintenance DATE,
    status VARCHAR(50) DEFAULT 'in_service',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inspection requests table
CREATE TABLE IF NOT EXISTS inspection_requests (
    id SERIAL PRIMARY KEY,
    external_id INTEGER,
    wagon_id INTEGER REFERENCES wagons(id),
    wagon_code VARCHAR(50),
    issue_description TEXT,
    urgency VARCHAR(20) DEFAULT 'normal',
    requested_date DATE,
    scheduled_date TIMESTAMP,
    location VARCHAR(200),
    status VARCHAR(50) DEFAULT 'requested',
    technician_name VARCHAR(100),
    findings TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Devis (Quotes) received table
CREATE TABLE IF NOT EXISTS devis_received (
    id SERIAL PRIMARY KEY,
    external_devis_id INTEGER,
    inspection_request_id INTEGER REFERENCES inspection_requests(id),
    wagon_code VARCHAR(50),
    final_amount DECIMAL(10,2),
    proposed_intervention_date DATE,
    status VARCHAR(50) DEFAULT 'received',
    validated_by VARCHAR(100),
    validated_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE,
    devis_id INTEGER REFERENCES devis_received(id),
    wagon_code VARCHAR(50),
    total_amount DECIMAL(10,2),
    intervention_date DATE,
    status VARCHAR(50) DEFAULT 'pending',
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notifications received log
CREATE TABLE IF NOT EXISTS notifications_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100),
    source VARCHAR(100),
    payload JSONB,
    processed BOOLEAN DEFAULT false,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspection_requests(status);
CREATE INDEX IF NOT EXISTS idx_devis_status ON devis_received(status);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_notifications_processed ON notifications_log(processed);

-- Insert sample wagons
INSERT INTO wagons (wagon_code, wagon_type, year_built, last_maintenance_date, next_scheduled_maintenance, status) VALUES
    ('WAG-001', 'Passenger Coach Standard', 2018, '2024-06-15', '2025-06-15', 'in_service'),
    ('WAG-002', 'Passenger Coach First Class', 2019, '2024-08-20', '2025-08-20', 'in_service'),
    ('WAG-003', 'Dining Car', 2017, '2024-05-10', '2025-05-10', 'in_service'),
    ('WAG-004', 'Passenger Coach Standard', 2016, '2024-03-01', '2025-03-01', 'in_maintenance'),
    ('WAG-005', 'Sleeper Car', 2020, '2024-09-05', '2025-09-05', 'in_service'),
    ('WAG-006', 'Passenger Coach Economy', 2015, '2024-04-12', '2025-04-12', 'in_service'),
    ('WAG-007', 'Luggage Van', 2018, '2024-07-22', '2025-07-22', 'in_service'),
    ('WAG-008', 'Passenger Coach Standard', 2019, '2024-02-28', '2025-02-28', 'in_service')
ON CONFLICT (wagon_code) DO NOTHING;
