"""
ERP DevMateriels (DEMAT) Simulation - Simulates the DevMateriels internal ERP system.
Receives notifications about inspections, devis, and orders.
Manages interventions, billing, and stock reservations.
"""
from flask import Flask, request, jsonify
from datetime import datetime, date
from decimal import Decimal
import os
import logging

from models import (
    get_all_clients,
    get_client_by_name,
    create_intervention,
    update_intervention_from_notification,
    get_interventions,
    create_invoice,
    get_invoices,
    create_stock_reservation,
    get_stock_reservations,
    log_notification,
    mark_notification_processed,
    get_notifications_log
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def serialize_record(record):
    """Serialize record for JSON response."""
    if record is None:
        return None
    
    result = dict(record)
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, date):
            result[key] = str(value)
        elif isinstance(value, Decimal):
            result[key] = float(value)
    return result


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'erp-devmateriels',
        'company': 'DevMateriels'
    })


# ==================== CLIENTS ====================

@app.route('/clients', methods=['GET'])
def list_clients():
    """Get all clients."""
    try:
        clients = get_all_clients()
        return jsonify({
            'clients': [serialize_record(c) for c in clients],
            'total': len(clients)
        })
    except Exception as e:
        logger.error(f"Error fetching clients: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/clients/<company_name>', methods=['GET'])
def get_client(company_name):
    """Get client by company name."""
    try:
        client = get_client_by_name(company_name)
        if client:
            return jsonify(serialize_record(client))
        return jsonify({'error': 'Client not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching client: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== INTERVENTIONS ====================

@app.route('/interventions', methods=['GET'])
def list_interventions():
    """Get all interventions."""
    try:
        status = request.args.get('status')
        client = request.args.get('client_company')
        
        interventions = get_interventions(status, client)
        return jsonify({
            'interventions': [serialize_record(i) for i in interventions],
            'total': len(interventions)
        })
    except Exception as e:
        logger.error(f"Error fetching interventions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/interventions/<int:intervention_id>', methods=['GET'])
def get_intervention(intervention_id):
    """Get intervention by ID."""
    try:
        interventions = get_interventions()
        intervention = next((i for i in interventions if i['id'] == intervention_id), None)
        
        if intervention:
            # Get stock reservations
            reservations = get_stock_reservations(intervention_id)
            result = serialize_record(intervention)
            result['stock_reservations'] = [serialize_record(r) for r in reservations]
            return jsonify(result)
        return jsonify({'error': 'Intervention not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching intervention: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/interventions/<int:intervention_id>/invoice', methods=['POST'])
def create_intervention_invoice(intervention_id):
    """Create invoice for an intervention."""
    try:
        invoice = create_invoice(intervention_id)
        if invoice:
            logger.info(f"Invoice created: {invoice['invoice_number']}")
            return jsonify(serialize_record(invoice)), 201
        return jsonify({'error': 'Intervention not found'}), 404
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== INVOICES ====================

@app.route('/invoices', methods=['GET'])
def list_invoices():
    """Get all invoices."""
    try:
        status = request.args.get('status')
        client = request.args.get('client_company')
        
        invoices = get_invoices(status, client)
        return jsonify({
            'invoices': [serialize_record(i) for i in invoices],
            'total': len(invoices)
        })
    except Exception as e:
        logger.error(f"Error fetching invoices: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== STOCK RESERVATIONS ====================

@app.route('/stock-reservations', methods=['GET'])
def list_stock_reservations():
    """Get all stock reservations."""
    try:
        status = request.args.get('status')
        intervention_id = request.args.get('intervention_id', type=int)
        
        reservations = get_stock_reservations(intervention_id, status)
        return jsonify({
            'reservations': [serialize_record(r) for r in reservations],
            'total': len(reservations)
        })
    except Exception as e:
        logger.error(f"Error fetching stock reservations: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== NOTIFICATIONS (Received from Notification Service) ====================

@app.route('/api/notifications', methods=['POST'])
def receive_notification():
    """
    Receive notification from DevMateriels Notification Service.
    This endpoint is called by the Notification Service.
    """
    try:
        data = request.get_json()
        
        event_type = data.get('event_type')
        event_data = data.get('event_data', {})
        
        logger.info(f"Received notification: {event_type}")
        
        # Log the notification
        notification = log_notification(event_type, 'NotificationService', data)
        
        # Process based on event type
        if event_type == 'inspection.requested':
            # Create new inspection intervention
            create_intervention(event_data, 'inspection')
            logger.info(f"Created inspection intervention for wagon {event_data.get('wagon_id')}")
            
        elif event_type == 'inspection.scheduled':
            # Update intervention with schedule
            update_intervention_from_notification(event_data)
            logger.info(f"Updated inspection schedule for wagon {event_data.get('wagon_id')}")
            
        elif event_type == 'inspection.completed':
            # Update intervention as completed
            update_intervention_from_notification(event_data)
            logger.info(f"Inspection completed for wagon {event_data.get('wagon_id')}")
            
        elif event_type == 'devis.generated':
            # Update intervention with devis info
            update_intervention_from_notification(event_data)
            logger.info(f"Devis generated for wagon {event_data.get('wagon_id')}")
            
        elif event_type == 'devis.validated':
            # Create repair intervention and invoice
            intervention = update_intervention_from_notification(event_data)
            if intervention and intervention.get('total_amount'):
                # Create invoice
                invoice = create_invoice(intervention['id'])
                if invoice:
                    logger.info(f"Invoice {invoice['invoice_number']} created for intervention {intervention['id']}")
                
                # Create stock reservations if parts info available
                parts = event_data.get('parts_needed', [])
                if parts:
                    create_stock_reservation(intervention['id'], parts)
                    logger.info(f"Stock reserved for intervention {intervention['id']}")
            
        elif event_type == 'devis.rejected':
            # Update intervention as cancelled
            event_data['status'] = 'cancelled'
            update_intervention_from_notification(event_data)
            logger.info(f"Devis rejected for wagon {event_data.get('wagon_id')}")
        
        # Mark notification as processed
        mark_notification_processed(notification['id'])
        
        return jsonify({
            'status': 'received',
            'notification_id': notification['id'],
            'event_type': event_type
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing notification: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/notifications', methods=['GET'])
def list_notifications():
    """Get notifications log."""
    try:
        processed = request.args.get('processed')
        if processed is not None:
            processed = processed.lower() == 'true'
        
        notifications = get_notifications_log(processed)
        return jsonify({
            'notifications': [serialize_record(n) for n in notifications],
            'total': len(notifications)
        })
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== DASHBOARD ====================

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Get dashboard summary."""
    try:
        clients = get_all_clients()
        interventions = get_interventions()
        invoices = get_invoices()
        reservations = get_stock_reservations()
        
        # Calculate revenue
        total_revenue = sum(float(i['amount_ht'] or 0) for i in invoices)
        paid_revenue = sum(float(i['amount_ht'] or 0) for i in invoices if i['status'] == 'paid')
        pending_revenue = sum(float(i['amount_ht'] or 0) for i in invoices if i['status'] in ['issued', 'draft'])
        
        return jsonify({
            'summary': {
                'total_clients': len(clients),
                'active_interventions': len([i for i in interventions if i['status'] in ['pending', 'scheduled', 'confirmed']]),
                'completed_interventions': len([i for i in interventions if i['status'] == 'completed']),
                'total_invoices': len(invoices),
                'pending_invoices': len([i for i in invoices if i['status'] in ['issued', 'draft']]),
                'active_reservations': len([r for r in reservations if r['status'] == 'reserved']),
                'total_revenue': total_revenue,
                'paid_revenue': paid_revenue,
                'pending_revenue': pending_revenue
            },
            'recent_interventions': [serialize_record(i) for i in interventions[:5]],
            'recent_invoices': [serialize_record(i) for i in invoices[:5]],
            'clients': [serialize_record(c) for c in clients]
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== REPORTS ====================

@app.route('/reports/client/<company_name>', methods=['GET'])
def client_report(company_name):
    """Get report for a specific client."""
    try:
        client = get_client_by_name(company_name)
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        
        interventions = get_interventions(client_company=company_name)
        invoices = get_invoices(client_company=company_name)
        
        return jsonify({
            'client': serialize_record(client),
            'statistics': {
                'total_interventions': len(interventions),
                'completed_interventions': len([i for i in interventions if i['status'] == 'completed']),
                'total_invoiced': sum(float(i['amount_ht'] or 0) for i in invoices),
                'total_paid': sum(float(i['amount_ht'] or 0) for i in invoices if i['status'] == 'paid'),
                'pending_payment': sum(float(i['amount_ht'] or 0) for i in invoices if i['status'] == 'issued')
            },
            'interventions': [serialize_record(i) for i in interventions],
            'invoices': [serialize_record(i) for i in invoices]
        })
    except Exception as e:
        logger.error(f"Error generating client report: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting ERP DevMateriels (DEMAT) simulation on port 5011")
    app.run(host='0.0.0.0', port=5011, debug=True)
