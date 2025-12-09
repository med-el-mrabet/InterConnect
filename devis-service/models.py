"""
Database models for Devis Service.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date, timedelta
from decimal import Decimal
import json

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://devis_user:devis_pass@localhost:5433/devis_db')


def get_db_connection():
    """Create a database connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


# ==================== PARTS MANAGEMENT ====================

def get_all_parts(category=None):
    """Get all parts, optionally filtered by category."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if category:
                cur.execute(
                    "SELECT * FROM parts WHERE category = %s ORDER BY reference",
                    (category,)
                )
            else:
                cur.execute("SELECT * FROM parts ORDER BY category, reference")
            return cur.fetchall()
    finally:
        conn.close()


def get_part_by_reference(reference):
    """Get part by reference code."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM parts WHERE reference = %s", (reference,))
            return cur.fetchone()
    finally:
        conn.close()


def get_part_by_id(part_id):
    """Get part by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM parts WHERE id = %s", (part_id,))
            return cur.fetchone()
    finally:
        conn.close()


def check_stock_availability(parts_list):
    """
    Check stock availability for a list of parts.
    Returns availability status and estimated restock dates if needed.
    """
    conn = get_db_connection()
    results = []
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for item in parts_list:
                reference = item.get('reference')
                quantity_needed = item.get('quantity', 1)
                
                cur.execute("SELECT * FROM parts WHERE reference = %s", (reference,))
                part = cur.fetchone()
                
                if not part:
                    results.append({
                        'reference': reference,
                        'found': False,
                        'available': False,
                        'error': 'Part not found in catalog'
                    })
                else:
                    available = part['stock_quantity'] >= quantity_needed
                    result = {
                        'reference': reference,
                        'name': part['name'],
                        'found': True,
                        'available': available,
                        'quantity_needed': quantity_needed,
                        'stock_quantity': part['stock_quantity'],
                        'catalog_price': float(part['catalog_price'])
                    }
                    
                    if not available:
                        shortage = quantity_needed - part['stock_quantity']
                        restock_date = date.today() + timedelta(days=part['lead_time_days'])
                        result['shortage'] = shortage
                        result['estimated_restock_date'] = str(restock_date)
                        result['lead_time_days'] = part['lead_time_days']
                    
                    results.append(result)
        
        return results
    finally:
        conn.close()


def update_stock(part_id, quantity_change, movement_type, reference_type=None, reference_id=None, notes=None):
    """Update stock quantity and record movement."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Update stock
            cur.execute("""
                UPDATE parts 
                SET stock_quantity = stock_quantity + %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (quantity_change, part_id))
            part = cur.fetchone()
            
            # Record movement
            cur.execute("""
                INSERT INTO stock_movements 
                    (part_id, movement_type, quantity, reference_type, reference_id, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (part_id, movement_type, quantity_change, reference_type, reference_id, notes))
            
            conn.commit()
            return part
    finally:
        conn.close()


# ==================== DEVIS MANAGEMENT ====================

def create_devis(data, items_with_stock):
    """Create a new devis (quote)."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Calculate totals
            total_parts_cost = sum(
                Decimal(str(item['catalog_price'])) * item['quantity_needed'] 
                for item in items_with_stock if item.get('found')
            )
            intervention_hours = Decimal(str(data.get('intervention_hours', 0)))
            hourly_rate = Decimal(str(data.get('hourly_rate', 85.00)))
            total_labor_cost = intervention_hours * hourly_rate
            inspection_forfait = Decimal('1360.00')  # 2 days * 85€/h * 8h
            
            discount = Decimal(str(data.get('discount_percentage', 0)))
            subtotal = total_parts_cost + total_labor_cost + inspection_forfait
            final_amount = subtotal * (1 - discount / 100)
            
            # Determine urgency-based intervention date
            proposed_date = data.get('proposed_intervention_date')
            if not proposed_date:
                # Default: 3 days for high urgency, 7 days for normal
                days_offset = 3 if data.get('urgency') == 'high' else 7
                proposed_date = date.today() + timedelta(days=days_offset)
            
            # Create devis
            cur.execute("""
                INSERT INTO devis 
                    (inspection_id, wagon_id, client_company, intervention_hours, hourly_rate,
                     inspection_forfait, total_parts_cost, total_labor_cost, discount_percentage,
                     final_amount, proposed_intervention_date, urgency, status, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s)
                RETURNING *
            """, (
                data.get('inspection_id'),
                data['wagon_id'],
                data['client_company'],
                intervention_hours,
                hourly_rate,
                inspection_forfait,
                total_parts_cost,
                total_labor_cost,
                discount,
                final_amount,
                proposed_date,
                data.get('urgency', 'normal'),
                data.get('notes')
            ))
            devis = cur.fetchone()
            
            # Create devis items
            for item in items_with_stock:
                if item.get('found'):
                    part = get_part_by_reference(item['reference'])
                    line_total = Decimal(str(item['catalog_price'])) * item['quantity_needed']
                    
                    cur.execute("""
                        INSERT INTO devis_items 
                            (devis_id, part_id, part_reference, part_name, quantity, 
                             catalog_price, negotiated_price, line_total, stock_available)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        devis['id'],
                        part['id'] if part else None,
                        item['reference'],
                        item['name'],
                        item['quantity_needed'],
                        item['catalog_price'],
                        item['catalog_price'],  # Initially same as catalog
                        float(line_total),
                        item['available']
                    ))
            
            conn.commit()
            return devis
    finally:
        conn.close()


def get_devis_by_id(devis_id):
    """Get devis by ID with all items."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get devis
            cur.execute("SELECT * FROM devis WHERE id = %s", (devis_id,))
            devis = cur.fetchone()
            
            if not devis:
                return None
            
            # Get items
            cur.execute("""
                SELECT * FROM devis_items WHERE devis_id = %s ORDER BY id
            """, (devis_id,))
            items = cur.fetchall()
            
            return {
                'devis': devis,
                'items': items
            }
    finally:
        conn.close()


def update_devis_negotiation(devis_id, discount_percentage=None, negotiated_parts=None, new_date=None):
    """Update devis with negotiated values."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get current devis
            cur.execute("SELECT * FROM devis WHERE id = %s", (devis_id,))
            devis = cur.fetchone()
            
            if not devis:
                return None
            
            # Update negotiated parts prices
            if negotiated_parts:
                for np in negotiated_parts:
                    cur.execute("""
                        UPDATE devis_items 
                        SET negotiated_price = %s, 
                            line_total = %s * quantity
                        WHERE devis_id = %s AND part_id = %s
                    """, (np['negotiated_price'], np['negotiated_price'], devis_id, np['part_id']))
            
            # Recalculate totals
            cur.execute("""
                SELECT COALESCE(SUM(line_total), 0) as total
                FROM devis_items WHERE devis_id = %s
            """, (devis_id,))
            parts_total = cur.fetchone()['total']
            
            # Apply new discount if provided
            new_discount = Decimal(str(discount_percentage)) if discount_percentage is not None else devis['discount_percentage']
            
            labor_cost = devis['total_labor_cost']
            inspection_forfait = devis['inspection_forfait']
            subtotal = Decimal(str(parts_total)) + labor_cost + inspection_forfait
            final_amount = subtotal * (1 - new_discount / 100)
            
            # Update devis
            update_fields = {
                'total_parts_cost': parts_total,
                'discount_percentage': new_discount,
                'final_amount': final_amount,
                'status': 'negotiating'
            }
            
            if new_date:
                update_fields['proposed_intervention_date'] = new_date
            
            cur.execute("""
                UPDATE devis 
                SET total_parts_cost = %s,
                    discount_percentage = %s,
                    final_amount = %s,
                    status = %s,
                    proposed_intervention_date = COALESCE(%s, proposed_intervention_date),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (
                update_fields['total_parts_cost'],
                update_fields['discount_percentage'],
                update_fields['final_amount'],
                update_fields['status'],
                new_date,
                devis_id
            ))
            
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def validate_devis(devis_id, confirmed_by, notes=None):
    """Validate and confirm devis as an order."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE devis 
                SET status = 'validated',
                    confirmed_by = %s,
                    notes = COALESCE(%s, notes),
                    validated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (confirmed_by, notes, devis_id))
            devis = cur.fetchone()
            
            if devis:
                # Reserve stock for validated devis
                cur.execute("SELECT * FROM devis_items WHERE devis_id = %s", (devis_id,))
                items = cur.fetchall()
                
                for item in items:
                    if item['part_id'] and item['stock_available']:
                        cur.execute("""
                            UPDATE parts 
                            SET stock_quantity = stock_quantity - %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (item['quantity'], item['part_id']))
                        
                        # Record stock movement
                        cur.execute("""
                            INSERT INTO stock_movements 
                                (part_id, movement_type, quantity, reference_type, reference_id, notes)
                            VALUES (%s, 'reservation', %s, 'devis', %s, %s)
                        """, (item['part_id'], -item['quantity'], devis_id, f"Reserved for order {devis_id}"))
            
            conn.commit()
            return devis
    finally:
        conn.close()


def reject_devis(devis_id, reason=None):
    """Reject a devis."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE devis 
                SET status = 'rejected',
                    notes = COALESCE(%s, notes),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (reason, devis_id))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_devis_by_status(status=None, client_company=None):
    """Get devis filtered by status and/or client."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM devis WHERE 1=1"
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
