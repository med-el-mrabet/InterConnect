"""
Database models for ERP DevMateriels (DEMAT) simulation.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime, date, timedelta
from decimal import Decimal
import uuid

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://erp_devmateriels_user:erp_devmateriels_pass@localhost:5436/erp_devmateriels_db')


def get_db_connection():
    """Create a database connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


# ==================== CLIENTS ====================

def get_all_clients():
    """Get all clients."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM clients ORDER BY company_name")
            return cur.fetchall()
    finally:
        conn.close()


def get_client_by_name(company_name):
    """Get client by company name."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM clients WHERE company_name = %s", (company_name,))
            return cur.fetchone()
    finally:
        conn.close()


# ==================== INTERVENTIONS ====================

def create_intervention(event_data, intervention_type='inspection'):
    """Create a new intervention from notification."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get client id
            client = get_client_by_name(event_data.get('client_company', 'WagonLits'))
            client_id = client['id'] if client else None
            
            status = 'pending'
            if intervention_type == 'inspection':
                if event_data.get('status') == 'scheduled':
                    status = 'scheduled'
                elif event_data.get('status') == 'completed':
                    status = 'completed'
            elif intervention_type == 'repair':
                status = 'scheduled'
            
            cur.execute("""
                INSERT INTO interventions 
                    (external_inspection_id, external_devis_id, client_id, client_company, 
                     wagon_code, intervention_type, scheduled_date, technician_assigned, 
                     status, total_amount, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (
                event_data.get('inspection_id'),
                event_data.get('devis_id'),
                client_id,
                event_data.get('client_company', 'WagonLits'),
                event_data.get('wagon_id'),
                intervention_type,
                event_data.get('scheduled_date') or event_data.get('intervention_date'),
                event_data.get('technician_name'),
                status,
                event_data.get('final_amount'),
                event_data.get('notes')
            ))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def update_intervention_from_notification(event_data):
    """Update existing intervention from notification."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Find existing intervention
            inspection_id = event_data.get('inspection_id')
            devis_id = event_data.get('devis_id')
            
            if inspection_id:
                cur.execute(
                    "SELECT * FROM interventions WHERE external_inspection_id = %s ORDER BY created_at DESC LIMIT 1",
                    (inspection_id,)
                )
            elif devis_id:
                cur.execute(
                    "SELECT * FROM interventions WHERE external_devis_id = %s ORDER BY created_at DESC LIMIT 1",
                    (devis_id,)
                )
            else:
                cur.execute(
                    "SELECT * FROM interventions WHERE wagon_code = %s ORDER BY created_at DESC LIMIT 1",
                    (event_data.get('wagon_id'),)
                )
            
            existing = cur.fetchone()
            
            if existing:
                # Update existing
                new_status = event_data.get('status', existing['status'])
                if new_status == 'validated':
                    new_status = 'confirmed'
                
                cur.execute("""
                    UPDATE interventions 
                    SET external_devis_id = COALESCE(%s, external_devis_id),
                        scheduled_date = COALESCE(%s, scheduled_date),
                        technician_assigned = COALESCE(%s, technician_assigned),
                        status = %s,
                        total_amount = COALESCE(%s, total_amount),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                """, (
                    event_data.get('devis_id'),
                    event_data.get('scheduled_date') or event_data.get('intervention_date'),
                    event_data.get('technician_name'),
                    new_status,
                    event_data.get('final_amount'),
                    existing['id']
                ))
                conn.commit()
                return cur.fetchone()
            else:
                # Create new
                return create_intervention(event_data)
    finally:
        conn.close()


def get_interventions(status=None, client_company=None):
    """Get interventions with optional filters."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM interventions WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            if client_company:
                query += " AND client_company = %s"
                params.append(client_company)
            
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


# ==================== INVOICES ====================

def create_invoice(intervention_id):
    """Create invoice for an intervention."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get intervention
            cur.execute("SELECT * FROM interventions WHERE id = %s", (intervention_id,))
            intervention = cur.fetchone()
            
            if not intervention:
                return None
            
            # Get client
            client = get_client_by_name(intervention['client_company'])
            
            # Calculate amounts
            amount_ht = Decimal(str(intervention['total_amount'] or 0))
            tva_rate = Decimal('20.00')
            amount_ttc = amount_ht * (1 + tva_rate / 100)
            
            # Generate invoice number
            invoice_number = f"FAC-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
            
            cur.execute("""
                INSERT INTO invoices 
                    (invoice_number, intervention_id, client_id, client_company,
                     amount_ht, tva_rate, amount_ttc, status, issued_date, due_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'issued', CURRENT_DATE, %s)
                RETURNING *
            """, (
                invoice_number,
                intervention_id,
                client['id'] if client else None,
                intervention['client_company'],
                amount_ht,
                tva_rate,
                amount_ttc,
                date.today() + timedelta(days=30)
            ))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_invoices(status=None, client_company=None):
    """Get invoices with optional filters."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM invoices WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            if client_company:
                query += " AND client_company = %s"
                params.append(client_company)
            
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


# ==================== STOCK RESERVATIONS ====================

def create_stock_reservation(intervention_id, parts):
    """Create stock reservations for intervention."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            reservations = []
            for part in parts:
                cur.execute("""
                    INSERT INTO stock_reservations 
                        (intervention_id, part_reference, part_name, quantity, status)
                    VALUES (%s, %s, %s, %s, 'reserved')
                    RETURNING *
                """, (
                    intervention_id,
                    part.get('reference'),
                    part.get('name'),
                    part.get('quantity', 1)
                ))
                reservations.append(cur.fetchone())
            
            conn.commit()
            return reservations
    finally:
        conn.close()


def get_stock_reservations(intervention_id=None, status=None):
    """Get stock reservations."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM stock_reservations WHERE 1=1"
            params = []
            
            if intervention_id:
                query += " AND intervention_id = %s"
                params.append(intervention_id)
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            query += " ORDER BY reserved_at DESC"
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


# ==================== NOTIFICATIONS ====================

def log_notification(event_type, source, payload):
    """Log received notification."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO notifications_log (event_type, source, payload)
                VALUES (%s, %s, %s)
                RETURNING *
            """, (event_type, source, Json(payload)))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def mark_notification_processed(notification_id):
    """Mark notification as processed."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE notifications_log 
                SET processed = true, processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (notification_id,))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_notifications_log(processed=None, limit=100):
    """Get notifications log."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if processed is not None:
                cur.execute(
                    "SELECT * FROM notifications_log WHERE processed = %s ORDER BY created_at DESC LIMIT %s",
                    (processed, limit)
                )
            else:
                cur.execute("SELECT * FROM notifications_log ORDER BY created_at DESC LIMIT %s", (limit,))
            return cur.fetchall()
    finally:
        conn.close()
