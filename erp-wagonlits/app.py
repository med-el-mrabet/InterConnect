"""
ERP WagonLits Simulation - Simulates the WagonLits ERP system.
Receives notifications from DevMateriels and can initiate inspection requests.
"""
from flask import Flask, request, jsonify
from datetime import datetime
import requests
import os
import logging

from models import (
    get_all_wagons,
    get_wagon_by_code,
    create_inspection_request,
    update_inspection_from_notification,
    get_inspection_requests,
    create_or_update_devis,
    get_devis_list,
    create_order,
    get_orders,
    log_notification,
    mark_notification_processed,
    get_notifications_log
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

API_GATEWAY_URL = os.getenv('API_GATEWAY_URL', 'http://localhost:5000')


def serialize_record(record):
    """Serialize record for JSON response."""
    if record is None:
        return None
    
    result = dict(record)
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'erp-wagonlits',
        'company': 'WagonLits'
    })


# ==================== WAGONS ====================

@app.route('/wagons', methods=['GET'])
def list_wagons():
    """Get all wagons."""
    try:
        wagons = get_all_wagons()
        return jsonify({
            'wagons': [serialize_record(w) for w in wagons],
            'total': len(wagons)
        })
    except Exception as e:
        logger.error(f"Error fetching wagons: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/wagons/<wagon_code>', methods=['GET'])
def get_wagon(wagon_code):
    """Get wagon by code."""
    try:
        wagon = get_wagon_by_code(wagon_code)
        if wagon:
            return jsonify(serialize_record(wagon))
        return jsonify({'error': 'Wagon not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching wagon: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== INSPECTION REQUESTS ====================

@app.route('/inspections', methods=['GET'])
def list_inspections():
    """Get all inspection requests."""
    try:
        status = request.args.get('status')
        inspections = get_inspection_requests(status)
        return jsonify({
            'inspections': [serialize_record(i) for i in inspections],
            'total': len(inspections)
        })
    except Exception as e:
        logger.error(f"Error fetching inspections: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/inspections/request', methods=['POST'])
def request_inspection():
    """
    Create a new inspection request and send to DevMateriels API.
    
    Expected payload:
    {
        "wagon_code": "WAG-001",
        "issue_description": "Brake system malfunction",
        "urgency": "high",
        "requested_date": "2024-01-15"
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('wagon_code'):
            return jsonify({'error': 'wagon_code is required'}), 400
        
        # Create local record
        inspection = create_inspection_request(data)
        
        # Send to DevMateriels API Gateway
        api_payload = {
            'wagon_id': data['wagon_code'],
            'client_company': 'WagonLits',
            'issue_description': data.get('issue_description'),
            'urgency': data.get('urgency', 'normal'),
            'requested_date': data.get('requested_date')
        }
        
        try:
            response = requests.post(
                f"{API_GATEWAY_URL}/api/inspection/request",
                json=api_payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                external_data = response.json()
                logger.info(f"Inspection request sent to DevMateriels: {external_data}")
                
                return jsonify({
                    'local_inspection': serialize_record(inspection),
                    'devmateriels_response': external_data,
                    'message': 'Inspection request sent successfully'
                }), 201
            else:
                logger.warning(f"DevMateriels API error: {response.status_code}")
                return jsonify({
                    'local_inspection': serialize_record(inspection),
                    'warning': f'Local record created but DevMateriels API returned {response.status_code}'
                }), 201
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to contact DevMateriels API: {e}")
            return jsonify({
                'local_inspection': serialize_record(inspection),
                'warning': 'Local record created but failed to contact DevMateriels API'
            }), 201
            
    except Exception as e:
        logger.error(f"Error creating inspection: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== DEVIS ====================

@app.route('/devis', methods=['GET'])
def list_devis():
    """Get all received devis."""
    try:
        status = request.args.get('status')
        devis = get_devis_list(status)
        return jsonify({
            'devis': [serialize_record(d) for d in devis],
            'total': len(devis)
        })
    except Exception as e:
        logger.error(f"Error fetching devis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devis/<int:devis_id>/validate', methods=['POST'])
def validate_devis(devis_id):
    """
    Validate a devis and send confirmation to DevMateriels.
    
    Expected payload:
    {
        "confirmed_by": "Jean Martin",
        "notes": "Approved for immediate intervention"
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('confirmed_by'):
            return jsonify({'error': 'confirmed_by is required'}), 400
        
        # Get the devis
        devis_list = get_devis_list()
        devis = next((d for d in devis_list if d['id'] == devis_id), None)
        
        if not devis:
            return jsonify({'error': 'Devis not found'}), 404
        
        # Send validation to DevMateriels
        try:
            response = requests.post(
                f"{API_GATEWAY_URL}/api/devis/{devis['external_devis_id']}/validate",
                json=data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                # Create local order
                order = create_order(devis_id, data['confirmed_by'])
                
                logger.info(f"Devis {devis_id} validated, order created: {order['order_number']}")
                return jsonify({
                    'order': serialize_record(order),
                    'message': 'Devis validated and order created'
                }), 201
            else:
                return jsonify({
                    'error': f'DevMateriels API returned {response.status_code}'
                }), response.status_code
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to contact DevMateriels API: {e}")
            return jsonify({'error': 'Failed to contact DevMateriels API'}), 503
            
    except Exception as e:
        logger.error(f"Error validating devis: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== ORDERS ====================

@app.route('/orders', methods=['GET'])
def list_orders():
    """Get all orders."""
    try:
        status = request.args.get('status')
        orders = get_orders(status)
        return jsonify({
            'orders': [serialize_record(o) for o in orders],
            'total': len(orders)
        })
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== NOTIFICATIONS (Received from DevMateriels) ====================

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
        notification = log_notification(event_type, 'DevMateriels', data)
        
        # Process based on event type
        if event_type in ['inspection.requested', 'inspection.scheduled', 'inspection.completed']:
            update_inspection_from_notification(event_data)
            
        elif event_type in ['devis.generated', 'devis.validated', 'devis.rejected']:
            create_or_update_devis(event_data)
        
        # Mark as processed
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
        wagons = get_all_wagons()
        inspections = get_inspection_requests()
        devis = get_devis_list()
        orders = get_orders()
        
        return jsonify({
            'summary': {
                'total_wagons': len(wagons),
                'wagons_in_service': len([w for w in wagons if w['status'] == 'in_service']),
                'wagons_in_maintenance': len([w for w in wagons if w['status'] == 'in_maintenance']),
                'pending_inspections': len([i for i in inspections if i['status'] in ['requested', 'scheduled']]),
                'pending_devis': len([d for d in devis if d['status'] == 'received']),
                'active_orders': len([o for o in orders if o['status'] in ['pending', 'confirmed']])
            },
            'recent_inspections': [serialize_record(i) for i in inspections[:5]],
            'recent_devis': [serialize_record(d) for d in devis[:5]],
            'recent_orders': [serialize_record(o) for o in orders[:5]]
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting ERP WagonLits simulation on port 5010")
    app.run(host='0.0.0.0', port=5010, debug=True)
