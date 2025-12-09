-- Devis Service Database Schema

-- Parts catalog table
CREATE TABLE IF NOT EXISTS parts (
    id SERIAL PRIMARY KEY,
    reference VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    catalog_price DECIMAL(10,2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    reorder_threshold INTEGER DEFAULT 10,
    reorder_quantity INTEGER DEFAULT 50,
    lead_time_days INTEGER DEFAULT 7,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Devis (Quotes) table
CREATE TABLE IF NOT EXISTS devis (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER,
    wagon_id VARCHAR(50) NOT NULL,
    client_company VARCHAR(100) NOT NULL,
    intervention_hours DECIMAL(5,2) DEFAULT 0,
    hourly_rate DECIMAL(10,2) DEFAULT 85.00,
    inspection_forfait DECIMAL(10,2) DEFAULT 1360.00,
    total_parts_cost DECIMAL(10,2) DEFAULT 0,
    total_labor_cost DECIMAL(10,2) DEFAULT 0,
    discount_percentage DECIMAL(5,2) DEFAULT 0,
    final_amount DECIMAL(10,2) DEFAULT 0,
    proposed_intervention_date DATE,
    urgency VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(50) DEFAULT 'draft',
    notes TEXT,
    confirmed_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    validated_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Devis line items table
CREATE TABLE IF NOT EXISTS devis_items (
    id SERIAL PRIMARY KEY,
    devis_id INTEGER REFERENCES devis(id) ON DELETE CASCADE,
    part_id INTEGER REFERENCES parts(id),
    part_reference VARCHAR(50),
    part_name VARCHAR(200),
    quantity INTEGER NOT NULL,
    catalog_price DECIMAL(10,2),
    negotiated_price DECIMAL(10,2),
    line_total DECIMAL(10,2),
    stock_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stock movements table
CREATE TABLE IF NOT EXISTS stock_movements (
    id SERIAL PRIMARY KEY,
    part_id INTEGER REFERENCES parts(id),
    movement_type VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    reference_type VARCHAR(50),
    reference_id INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_parts_reference ON parts(reference);
CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category);
CREATE INDEX IF NOT EXISTS idx_devis_status ON devis(status);
CREATE INDEX IF NOT EXISTS idx_devis_client ON devis(client_company);
CREATE INDEX IF NOT EXISTS idx_devis_items_devis ON devis_items(devis_id);

-- Insert sample parts for wagon maintenance
INSERT INTO parts (reference, name, description, category, catalog_price, stock_quantity, reorder_threshold) VALUES
    -- Brake system parts
    ('BP-001', 'Plaquette de frein standard', 'Plaquette de frein pour wagon passagers', 'Freinage', 45.00, 120, 20),
    ('BP-002', 'Plaquette de frein haute performance', 'Plaquette de frein renforcée', 'Freinage', 78.50, 45, 15),
    ('BD-001', 'Disque de frein 420mm', 'Disque de frein ventilé', 'Freinage', 320.00, 25, 8),
    ('BD-002', 'Disque de frein 380mm', 'Disque de frein standard', 'Freinage', 280.00, 30, 10),
    ('BC-001', 'Câble de frein de service', 'Câble acier tressé', 'Freinage', 65.00, 80, 15),
    
    -- Hydraulic parts
    ('HL-001', 'Joint hydraulique standard', 'Joint torique 50mm', 'Hydraulique', 12.50, 200, 50),
    ('HL-002', 'Flexible hydraulique 1m', 'Flexible haute pression', 'Hydraulique', 85.00, 60, 15),
    ('HL-003', 'Pompe hydraulique principale', 'Pompe 250 bar', 'Hydraulique', 1250.00, 8, 3),
    ('HL-004', 'Vérin hydraulique 100mm', 'Vérin double effet', 'Hydraulique', 450.00, 15, 5),
    
    -- Electrical parts
    ('EL-001', 'Connecteur électrique 12 broches', 'Connecteur étanche IP67', 'Électricité', 28.00, 150, 30),
    ('EL-002', 'Câble électrique principal 5m', 'Câble multiconducteur', 'Électricité', 95.00, 40, 10),
    ('EL-003', 'Relais de puissance 24V', 'Relais 40A', 'Électricité', 35.00, 100, 25),
    ('EL-004', 'Capteur de vitesse', 'Capteur inductif', 'Électricité', 180.00, 20, 8),
    
    -- Suspension parts
    ('SP-001', 'Ressort de suspension primaire', 'Ressort hélicoïdal acier', 'Suspension', 420.00, 18, 6),
    ('SP-002', 'Amortisseur hydraulique', 'Amortisseur réglable', 'Suspension', 580.00, 12, 4),
    ('SP-003', 'Silent bloc suspension', 'Bloc caoutchouc/métal', 'Suspension', 75.00, 80, 20),
    
    -- Coupling parts
    ('CP-001', 'Attelage automatique', 'Attelage type Scharfenberg', 'Attelage', 2800.00, 4, 2),
    ('CP-002', 'Tampon de choc', 'Tampon élastomère', 'Attelage', 350.00, 16, 6),
    
    -- Door system parts
    ('DR-001', 'Moteur de porte', 'Moteur électrique 24V', 'Portes', 680.00, 10, 4),
    ('DR-002', 'Rail de guidage porte', 'Rail aluminium 2m', 'Portes', 145.00, 25, 8),
    ('DR-003', 'Capteur obstacle porte', 'Capteur infrarouge', 'Portes', 95.00, 35, 10)
ON CONFLICT (reference) DO NOTHING;
