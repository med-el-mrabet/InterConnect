"""
API Gateway - Central entry point for DevMateriels microservices.
Routes requests to appropriate backend services.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Service URLs from environment
PLANNING_SERVICE_URL = os.getenv('PLANNING_SERVICE_URL', 'http://localhost:5001')
DEVIS_SERVICE_URL = os.getenv('DEVIS_SERVICE_URL', 'http://localhost:5002')
NOTIFICATION_SERVICE_URL = os.getenv('NOTIFICATION_SERVICE_URL', 'http://localhost:5003')


def forward_request(service_url, path, method='GET', data=None, params=None):
    """Forward request to a backend service."""
    url = f"{service_url}{path}"
    try:
        if method == 'GET':
            response = requests.get(url, params=params, timeout=30)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, json=data, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, timeout=30)
        else:
            return jsonify({'error': 'Unsupported method'}), 405
        
        return response.json(), response.status_code
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error to {url}")
        return {'error': f'Service unavailable: {service_url}'}, 503
    except requests.exceptions.Timeout:
        logger.error(f"Timeout connecting to {url}")
        return {'error': 'Service timeout'}, 504
    except Exception as e:
        logger.error(f"Error forwarding request: {e}")
        return {'error': str(e)}, 500


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'api-gateway'
    })


# ==================== INSPECTION ENDPOINTS ====================

@app.route('/api/inspection/request', methods=['POST'])
def request_inspection():
    """
    Request a technical inspection.
    Returns available slots with IDs for scheduling.
    """
    data = request.get_json()
    logger.info(f"Inspection request received for wagon: {data.get('wagon_id')}")
    return forward_request(PLANNING_SERVICE_URL, '/inspection/request', 'POST', data)


@app.route('/api/inspection/<int:inspection_id>', methods=['GET'])
def get_inspection(inspection_id):
    """Get inspection details by ID."""
    return forward_request(PLANNING_SERVICE_URL, f'/inspection/{inspection_id}', 'GET')


@app.route('/api/inspection/schedule/<int:slot_id>', methods=['POST'])
def schedule_by_slot(slot_id):
    """
    Schedule an inspection using a slot ID.
    Simple method - just provide slot_id and location.
    
    Expected payload:
    {
        "inspection_id": 1,
        "location": "Dépôt Paris Nord"
    }
    """
    data = request.get_json()
    logger.info(f"Scheduling inspection {data.get('inspection_id')} via slot {slot_id}")
    return forward_request(PLANNING_SERVICE_URL, f'/inspection/schedule/{slot_id}', 'POST', data)


@app.route('/api/inspection/<int:inspection_id>/schedule', methods=['POST'])
def schedule_inspection(inspection_id):
    """
    Schedule an inspection with confirmed date and location (legacy method).
    
    Expected payload:
    {
        "scheduled_date": "2024-01-16T09:00:00",
        "location": "Depot Paris Nord",
        "technician_id": 1
    }
    """
    data = request.get_json()
    logger.info(f"Scheduling inspection {inspection_id}")
    return forward_request(PLANNING_SERVICE_URL, f'/inspection/{inspection_id}/schedule', 'POST', data)


@app.route('/api/inspection/<int:inspection_id>/complete', methods=['POST'])
def complete_inspection(inspection_id):
    """
    Mark inspection as completed and provide findings.
    
    Expected payload:
    {
        "findings": "Brake pads worn, hydraulic leak detected",
        "parts_needed": [
            {"reference": "BP-001", "quantity": 4},
            {"reference": "HL-002", "quantity": 1}
        ],
        "estimated_repair_hours": 8
    }
    """
    data = request.get_json()
    logger.info(f"Completing inspection {inspection_id}")
    return forward_request(PLANNING_SERVICE_URL, f'/inspection/{inspection_id}/complete', 'POST', data)


@app.route('/api/inspection/availability', methods=['GET'])
def get_availability():
    """
    Get available slots for inspection with slot IDs.
    
    Query params:
    - start_date: Start date for availability search
    - end_date: End date for availability search
    """
    params = {
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date')
    }
    return forward_request(PLANNING_SERVICE_URL, '/inspection/availability', 'GET', params=params)


# ==================== DEVIS (QUOTE) ENDPOINTS ====================

@app.route('/api/devis/generate', methods=['POST'])
def generate_devis():
    """
    Generate a quote (devis) after inspection.
    Returns stock status and required modifications.
    
    Expected payload:
    {
        "inspection_id": 1,
        "wagon_id": "WAG-001",
        "client_company": "WagonLits",
        "parts": [
            {"reference": "BP-001", "quantity": 4},
            {"reference": "HL-002", "quantity": 1}
        ],
        "intervention_hours": 8,
        "proposed_intervention_date": "2024-01-20",
        "urgency": "high"
    }
    """
    data = request.get_json()
    logger.info(f"Generating devis for inspection: {data.get('inspection_id')}")
    return forward_request(DEVIS_SERVICE_URL, '/devis/generate', 'POST', data)


@app.route('/api/devis/<int:devis_id>', methods=['GET'])
def get_devis(devis_id):
    """Get quote details by ID."""
    return forward_request(DEVIS_SERVICE_URL, f'/devis/{devis_id}', 'GET')


@app.route('/api/devis/<int:devis_id>/negotiate', methods=['PUT'])
def negotiate_devis(devis_id):
    """
    Negotiate quote prices.
    
    Expected payload:
    {
        "discount_percentage": 10,
        "negotiated_parts": [
            {"part_id": 1, "negotiated_price": 45.00}
        ],
        "new_intervention_date": "2024-01-22"
    }
    """
    data = request.get_json()
    logger.info(f"Negotiating devis {devis_id}")
    return forward_request(DEVIS_SERVICE_URL, f'/devis/{devis_id}/negotiate', 'PUT', data)


@app.route('/api/devis/<int:devis_id>/validate', methods=['POST'])
def validate_devis(devis_id):
    """
    Validate and confirm the quote as an order.
    Sends notifications to both ERPs via Kafka.
    
    Expected payload:
    {
        "confirmed_by": "John Doe",
        "notes": "Urgent repair needed"
    }
    """
    data = request.get_json()
    logger.info(f"Validating devis {devis_id}")
    return forward_request(DEVIS_SERVICE_URL, f'/devis/{devis_id}/validate', 'POST', data)


@app.route('/api/devis/<int:devis_id>/reject', methods=['POST'])
def reject_devis(devis_id):
    """Reject a quote."""
    data = request.get_json()
    logger.info(f"Rejecting devis {devis_id}")
    return forward_request(DEVIS_SERVICE_URL, f'/devis/{devis_id}/reject', 'POST', data)


# ==================== STOCK ENDPOINTS ====================

@app.route('/api/stock/parts', methods=['GET'])
def get_parts():
    """Get all available parts."""
    return forward_request(DEVIS_SERVICE_URL, '/stock/parts', 'GET')


@app.route('/api/stock/parts/<reference>', methods=['GET'])
def get_part_by_reference(reference):
    """Get part details by reference."""
    return forward_request(DEVIS_SERVICE_URL, f'/stock/parts/{reference}', 'GET')


@app.route('/api/stock/check', methods=['POST'])
def check_stock():
    """
    Check stock availability for parts.
    Returns detailed status and suggestions.
    
    Expected payload:
    {
        "parts": [
            {"reference": "BP-001", "quantity": 4},
            {"reference": "HL-002", "quantity": 1}
        ]
    }
    """
    data = request.get_json()
    return forward_request(DEVIS_SERVICE_URL, '/stock/check', 'POST', data)


# ==================== NOTIFICATION ENDPOINTS ====================

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """Get all notifications."""
    params = {
        'status': request.args.get('status'),
        'target_erp': request.args.get('target_erp')
    }
    return forward_request(NOTIFICATION_SERVICE_URL, '/notifications', 'GET', params=params)


@app.route('/api/notifications/<int:notification_id>', methods=['GET'])
def get_notification(notification_id):
    """Get notification by ID."""
    return forward_request(NOTIFICATION_SERVICE_URL, f'/notifications/{notification_id}', 'GET')


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    logger.info("Starting API Gateway on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
