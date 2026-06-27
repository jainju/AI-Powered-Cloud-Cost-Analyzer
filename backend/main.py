"""FastAPI application entry point for the AI Cloud Cost Detective backend.

Creates and configures the ASGI application with middleware, routers,
global error handlers, and full dependency injection wiring.

Requirements: 1.1, 1.5, 5.2
"""

import logging
import sys

from fastapi import FastAPI

from backend.config.logging import setup_logging
from backend.config.settings import Settings
from backend.error_handlers import register_error_handlers
from backend.middleware.correlation import CorrelationIdMiddleware
from backend.middleware.request_logging import RequestLoggingMiddleware
from backend.routers import health, scan
from backend.services.aws_client import AWSClientFactory
from backend.services.resource_detector import ResourceDetector
from backend.services.scan_service import ScanService
from backend.services.scanners.ec2 import EC2Scanner
from backend.services.scanners.s3 import S3Scanner
from backend.services.scanners.rds import RDSScanner
from backend.services.scanners.lambda_scanner import LambdaScanner
from backend.services.scanners.dynamodb import DynamoDBScanner
from backend.services.scanners.elb import ELBScanner
from backend.services.scanners.cloudfront import CloudFrontScanner
from backend.services.scanners.iam import IAMScanner


def _validate_startup_dependencies() -> None:
    """Verify that all required dependencies are importable at startup.

    Fails with a clear error message if any critical dependency is missing.

    Raises:
        SystemExit: If a required dependency cannot be imported.
    """
    required_modules = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("boto3", "boto3"),
        ("pydantic", "pydantic"),
        ("pydantic_settings", "pydantic-settings"),
    ]

    missing = []
    for module_name, package_name in required_modules:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print(
            f"ERROR: Missing required dependencies: {', '.join(missing)}. "
            f"Install them with: pip install {' '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Performs startup validation, loads settings, configures logging,
    wires the full dependency chain, registers middleware and routers.

    Returns:
        A fully configured FastAPI application instance.
    """
    # Validate that all required dependencies are importable
    _validate_startup_dependencies()

    # Load application settings from environment / .env file
    settings = Settings()

    # Configure structured JSON logging with the configured level
    setup_logging(settings.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Starting AI Cloud Cost Detective backend")

    # Create FastAPI app
    application = FastAPI(title="AI Cloud Cost Detective", version="1.0.0")

    # Register middleware (order matters: last added = first executed)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(CorrelationIdMiddleware)

    # Register global exception handlers
    register_error_handlers(application)

    # Include routers
    application.include_router(health.router)
    application.include_router(scan.router)

    # Wire dependency injection chain:
    # Settings → AWSClientFactory → scanners → ResourceDetector → ScanService
    aws_client_factory = AWSClientFactory(settings)

    # Instantiate all scanners
    scanners = [
        EC2Scanner(),
        S3Scanner(),
        RDSScanner(),
        LambdaScanner(),
        DynamoDBScanner(),
        ELBScanner(),
        CloudFrontScanner(),
        IAMScanner(),
    ]

    # Create ResourceDetector with all scanners
    resource_detector = ResourceDetector(
        client_factory=aws_client_factory,
        scanners=scanners,
        settings=settings,
    )

    # Create ScanService and store in app state for access by routers
    scan_service = ScanService(detector=resource_detector)
    application.state.scan_service = scan_service

    logger.info(
        "Application configured with %d scanners across %d regions",
        len(scanners),
        len(settings.aws_regions),
    )

    return application


app = create_app()
