"""
Configuration utilities for microservices.
"""
import os


class Config:
    """Base configuration."""
    DEBUG = False
    TESTING = False
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:pass@localhost:5432/db')
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    
    # Service URLs
    PLANNING_SERVICE_URL = os.getenv('PLANNING_SERVICE_URL', 'http://localhost:5001')
    DEVIS_SERVICE_URL = os.getenv('DEVIS_SERVICE_URL', 'http://localhost:5002')
    NOTIFICATION_SERVICE_URL = os.getenv('NOTIFICATION_SERVICE_URL', 'http://localhost:5003')
    ERP_WAGONLITS_URL = os.getenv('ERP_WAGONLITS_URL', 'http://localhost:5010')
    ERP_DEVMATERIELS_URL = os.getenv('ERP_DEVMATERIELS_URL', 'http://localhost:5011')
    API_GATEWAY_URL = os.getenv('API_GATEWAY_URL', 'http://localhost:5000')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True


def get_config():
    """Get configuration based on environment."""
    env = os.getenv('FLASK_ENV', 'development')
    configs = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig
    }
    return configs.get(env, DevelopmentConfig)
