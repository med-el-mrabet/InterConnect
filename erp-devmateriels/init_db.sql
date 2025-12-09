-- ERP DevMateriels (DEMAT) Database Schema

-- Clients table
CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) UNIQUE NOT NULL,
    contact_name VARCHAR(100),
    contact_email VARCHAR(150),
    contact_phone VARCHAR(20),
    address TEXT,
    contract_type VARCHAR(50),
    annual_contract_value DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Interventions table
CREATE TABLE IF NOT EXISTS interventions (
    id SERIAL PRIMARY KEY,
    external_inspection_id INTEGER,
    external_devis_id INTEGER,
    client_id INTEGER REFERENCES clients(id),
    client_company VARCHAR(100),
    wagon_code VARCHAR(50),
    intervention_type VARCHAR(50) DEFAULT 'curative',
    scheduled_date DATE,
    completed_date DATE,
    technician_assigned VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    total_amount DECIMAL(10,2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE,
    intervention_id INTEGER REFERENCES interventions(id),
    client_id INTEGER REFERENCES clients(id),
    client_company VARCHAR(100),
    amount_ht DECIMAL(10,2),
    tva_rate DECIMAL(5,2) DEFAULT 20.00,
    amount_ttc DECIMAL(10,2),
    status VARCHAR(50) DEFAULT 'draft',
    issued_date DATE,
    due_date DATE,
    paid_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stock reservations table
CREATE TABLE IF NOT EXISTS stock_reservations (
    id SERIAL PRIMARY KEY,
    intervention_id INTEGER REFERENCES interventions(id),
    part_reference VARCHAR(50),
    part_name VARCHAR(200),
    quantity INTEGER,
    reserved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'reserved'
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
CREATE INDEX IF NOT EXISTS idx_interventions_status ON interventions(status);
CREATE INDEX IF NOT EXISTS idx_interventions_client ON interventions(client_company);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_stock_reservations_status ON stock_reservations(status);

-- Insert client data
INSERT INTO clients (company_name, contact_name, contact_email, contact_phone, contract_type, annual_contract_value) VALUES
    ('WagonLits', 'Pierre Durand', 'pierre.durand@wagonlits.fr', '+33 1 45 67 89 00', 'annualized', 2500000.00),
    ('ConstructWagons', 'Maria Garcia', 'maria.garcia@constructwagons.com', '+34 91 234 5678', 'on_demand', 0)
ON CONFLICT (company_name) DO NOTHING;
