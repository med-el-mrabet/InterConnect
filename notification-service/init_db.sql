-- Notification Service Database Schema

-- Notifications log table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    event_id VARCHAR(100),
    source_service VARCHAR(100),
    target_erp VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    http_status_code INTEGER,
    response_body TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notification templates table
CREATE TABLE IF NOT EXISTS notification_templates (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) UNIQUE NOT NULL,
    template_wagonlits JSONB,
    template_devmateriels JSONB,
    description TEXT,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_notifications_event_type ON notifications(event_type);
CREATE INDEX IF NOT EXISTS idx_notifications_target ON notifications(target_erp);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);

-- Insert notification templates
INSERT INTO notification_templates (event_type, template_wagonlits, template_devmateriels, description, active) VALUES
    ('inspection.requested', 
     '{"type": "INSPECTION_REQUEST", "action": "NEW_INSPECTION_REQUESTED"}',
     '{"type": "INSPECTION_REQUEST", "action": "INSPECTION_RECEIVED"}',
     'When a new inspection is requested', true),
    
    ('inspection.scheduled',
     '{"type": "INSPECTION_SCHEDULED", "action": "INSPECTION_DATE_CONFIRMED"}',
     '{"type": "INSPECTION_SCHEDULED", "action": "TECHNICIAN_ASSIGNED"}',
     'When an inspection date is confirmed', true),
    
    ('inspection.completed',
     '{"type": "INSPECTION_COMPLETED", "action": "REPORT_AVAILABLE"}',
     '{"type": "INSPECTION_COMPLETED", "action": "DEVIS_GENERATION_REQUIRED"}',
     'When inspection is completed with findings', true),
    
    ('devis.generated',
     '{"type": "DEVIS_GENERATED", "action": "QUOTE_RECEIVED"}',
     '{"type": "DEVIS_GENERATED", "action": "QUOTE_SENT_TO_CLIENT"}',
     'When a new quote is generated', true),
    
    ('devis.validated',
     '{"type": "ORDER_CONFIRMED", "action": "PREPARE_INTERVENTION"}',
     '{"type": "ORDER_CONFIRMED", "action": "SCHEDULE_INTERVENTION_AND_BILLING"}',
     'When a quote is validated as an order', true),
    
    ('devis.rejected',
     '{"type": "DEVIS_REJECTED", "action": "QUOTE_DECLINED"}',
     '{"type": "DEVIS_REJECTED", "action": "ARCHIVE_QUOTE"}',
     'When a quote is rejected', true)
ON CONFLICT (event_type) DO NOTHING;
