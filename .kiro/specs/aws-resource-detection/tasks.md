# Implementation Plan: AWS Resource Detection

## Overview

This plan implements a Python FastAPI backend in `backend/` that connects to an AWS account and detects all created resources across multiple services and regions. The implementation follows a layered architecture with per-service scanners, concurrency control via asyncio, and Pydantic models for validation.

## Tasks

- [x] 1. Set up project structure and configuration
  - [x] 1.1 Create backend directory structure and dependencies
    - Create `backend/` directory with sub-modules: `routers/`, `services/`, `services/scanners/`, `models/`, `config/`, `middleware/`, `tests/`, `tests/test_scanners/`
    - Add `__init__.py` files to each module
    - Create `backend/requirements.txt` with pinned dependencies: `fastapi==0.115.0`, `uvicorn==0.30.6`, `boto3==1.35.0`, `pydantic==2.9.0`, `pydantic-settings==2.5.0`, `python-dotenv==1.0.1`, `httpx==0.27.2`, `pytest==8.3.3`, `pytest-asyncio==0.24.0`, `hypothesis==6.112.0`
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 1.2 Implement configuration management with Pydantic Settings
    - Create `backend/config/settings.py` with `Settings` class extending `BaseSettings`
    - Define fields: `aws_access_key_id`, `aws_secret_access_key`, `aws_default_region` (default "us-east-1"), `aws_session_token` (optional), `aws_regions` (list, default ["us-east-1"]), `max_concurrent_api_calls` (default 10), `max_retry_attempts` (default 3), `scan_timeout_seconds` (default 300), `log_level` (Literal, default "INFO")
    - Add `field_validator` for `aws_regions` to parse comma-separated strings
    - Add validators for: region name format, positive integers for rate limiting, valid log level
    - Configure `.env` file loading with environment variable precedence
    - _Requirements: 2.1, 2.2, 2.6, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 1.3 Write property tests for configuration validation
    - **Property 5: Configuration Validation — Missing Required Values**
    - **Property 6: Configuration Validation — Invalid Values**
    - **Validates: Requirements 2.3, 2.7, 6.3, 6.5**

- [x] 2. Implement data models and response schemas
  - [x] 2.1 Create Pydantic models for resources and responses
    - Create `backend/models/resource.py` with `DetectedResource` model (fields: `resource_id`, `resource_type`, `service`, `region`, `created_at` as `Optional[str]`, `state`)
    - Create `backend/models/scan.py` with `ScanFailure`, `ScanSummary`, `ResourceInventory`, `ScanResponse`, `ErrorResponse`, `HealthResponse` models
    - Ensure `created_at` is serialized as `null` (not omitted) when None by using appropriate Pydantic config
    - _Requirements: 4.3, 5.1, 5.4, 5.5_

  - [ ]* 2.2 Write property tests for data models
    - **Property 1: Serialization Round-Trip**
    - **Property 2: Resource Schema Completeness**
    - **Property 4: Null Field Preservation**
    - **Validates: Requirements 3.2, 4.3, 5.5, 5.6**

- [x] 3. Implement AWS client and authentication
  - [x] 3.1 Create AWS Client Factory with credential validation
    - Create `backend/services/aws_client.py` with `AWSClientFactory` class
    - Implement `__init__` accepting `Settings`, creating boto3 session with credentials
    - Implement `validate_credentials()` calling STS `get_caller_identity` to verify auth
    - Implement `create_client(service_name, region)` returning a configured boto3 client
    - Implement `get_valid_regions()` returning validated region list
    - Raise clear errors with missing variable names when credentials are absent
    - Raise authentication errors with AWS failure reason when credentials are invalid
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7_

  - [x] 3.2 Implement retry logic with exponential backoff
    - Create a retry decorator/utility in `backend/services/retry.py`
    - Implement exponential backoff: initial delay 1s, multiplier 2, max delay cap 30s, max attempts from settings
    - Only retry on `ThrottlingException` and `RequestLimitExceeded` errors
    - Log each retry at WARNING level with service, operation, attempt number
    - Log final failure at ERROR level with full details
    - _Requirements: 8.1, 8.3_

  - [ ]* 3.3 Write property test for exponential backoff timing
    - **Property 13: Exponential Backoff Timing**
    - **Validates: Requirements 8.1**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement service scanners
  - [x] 5.1 Create base scanner interface
    - Create `backend/services/scanners/base.py` with abstract `BaseScanner` class
    - Define `service_name` (str), `is_global` (bool, default False) class attributes
    - Define abstract `async def scan(self, client, region) -> List[DetectedResource]` method
    - _Requirements: 3.1, 3.3_

  - [x] 5.2 Implement EC2 scanner
    - Create `backend/services/scanners/ec2.py` with `EC2Scanner` class
    - Implement scanning for: instances (`describe_instances`), volumes (`describe_volumes`), snapshots (`describe_snapshots`), elastic IPs (`describe_addresses`)
    - Handle pagination for all EC2 API calls
    - Map each resource to `DetectedResource` with appropriate fields
    - Set `is_global = False` (regional service)
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 5.3 Implement S3 scanner
    - Create `backend/services/scanners/s3.py` with `S3Scanner` class
    - Implement scanning for buckets using `list_buckets`
    - Set `is_global = True` (global service)
    - Map bucket data to `DetectedResource` objects
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.4 Implement RDS scanner
    - Create `backend/services/scanners/rds.py` with `RDSScanner` class
    - Implement scanning for: DB instances (`describe_db_instances`) and DB clusters (`describe_db_clusters`)
    - Handle pagination
    - Set `is_global = False`
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 5.5 Implement Lambda scanner
    - Create `backend/services/scanners/lambda_scanner.py` with `LambdaScanner` class
    - Implement scanning for functions using `list_functions`
    - Handle pagination
    - Set `is_global = False`
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 5.6 Implement DynamoDB scanner
    - Create `backend/services/scanners/dynamodb.py` with `DynamoDBScanner` class
    - Implement scanning for tables using `list_tables` + `describe_table` for each
    - Handle pagination
    - Set `is_global = False`
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 5.7 Implement ELB scanner
    - Create `backend/services/scanners/elb.py` with `ELBScanner` class
    - Implement scanning for load balancers using `describe_load_balancers` (ELBv2)
    - Handle pagination
    - Set `is_global = False`
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 5.8 Implement CloudFront scanner
    - Create `backend/services/scanners/cloudfront.py` with `CloudFrontScanner` class
    - Implement scanning for distributions using `list_distributions`
    - Handle pagination
    - Set `is_global = True`
    - _Requirements: 3.1, 3.2, 3.3, 3.6_

  - [x] 5.9 Implement IAM scanner
    - Create `backend/services/scanners/iam.py` with `IAMScanner` class
    - Implement scanning for users (`list_users`) and roles (`list_roles`)
    - Handle pagination
    - Set `is_global = True`
    - _Requirements: 3.1, 3.2, 3.3, 3.6_

  - [ ]* 5.10 Write property test for scanner invocation pattern
    - **Property 7: Scanner Invocation Pattern**
    - **Validates: Requirements 2.6, 3.3**

  - [ ]* 5.11 Write property test for pagination completeness
    - **Property 8: Pagination Completeness**
    - **Validates: Requirements 3.6**

- [x] 6. Implement resource detector orchestration
  - [x] 6.1 Create Resource Detector with concurrency control
    - Create `backend/services/resource_detector.py` with `ResourceDetector` class
    - Accept `AWSClientFactory`, list of `BaseScanner` instances, and `Settings`
    - Implement `detect_all()` method that:
      - Invokes regional scanners once per configured region
      - Invokes global scanners exactly once
      - Uses `asyncio.Semaphore(max_concurrent_api_calls)` for concurrency limiting
      - Wraps boto3 calls with `asyncio.to_thread()` for thread pool execution
      - Wraps entire operation in `asyncio.wait_for(timeout=scan_timeout_seconds)`
      - Catches per-service errors, records `ScanFailure`, continues scanning
      - On timeout, preserves partial results and sets `summary.timed_out = True`
    - Build `ResourceInventory` with correct summary aggregation
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 8.2_

  - [ ]* 6.2 Write property test for ResourceInventory aggregation
    - **Property 3: ResourceInventory Aggregation Correctness**
    - **Validates: Requirements 3.4, 3.5, 5.4, 8.3**

  - [ ]* 6.3 Write property test for concurrency limit enforcement
    - **Property 14: Concurrency Limit Enforcement**
    - **Validates: Requirements 8.2**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement middleware and logging
  - [x] 8.1 Create structured JSON logging configuration
    - Create `backend/config/logging.py` with structured JSON formatter
    - Ensure every log entry includes: `timestamp` (ISO 8601), `level`, `correlation_id`, `message`
    - Configure log levels per requirement: ERROR for failures, WARNING for retries, INFO for request lifecycle
    - Integrate with Settings `log_level` for configurable verbosity
    - _Requirements: 7.1, 7.6_

  - [x] 8.2 Implement correlation ID middleware
    - Create `backend/middleware/correlation.py` with ASGI middleware
    - Generate a UUID per incoming request
    - Store in request state for access throughout request lifecycle
    - Inject into all log entries produced during request processing
    - _Requirements: 7.4_

  - [x] 8.3 Implement request logging middleware
    - Create `backend/middleware/request_logging.py` with ASGI middleware
    - Log request method, path, response status code, and response time in milliseconds at INFO level
    - _Requirements: 7.2_

  - [ ]* 8.4 Write property test for structured log field completeness
    - **Property 10: Structured Log Field Completeness**
    - **Validates: Requirements 7.1**

  - [ ]* 8.5 Write property test for correlation ID consistency
    - **Property 11: Correlation ID Consistency**
    - **Validates: Requirements 7.4**

  - [ ]* 8.6 Write property test for log level correctness
    - **Property 12: Log Level Correctness**
    - **Validates: Requirements 7.6**

- [x] 9. Implement API routers and error handling
  - [x] 9.1 Create health check endpoint
    - Create `backend/routers/health.py` with `GET /health` route
    - Return `HealthResponse` with `status: "healthy"` and `service: "ai-cloud-cost-detective"`
    - _Requirements: 1.3_

  - [x] 9.2 Create scan endpoint with Scan Service
    - Create `backend/services/scan_service.py` with `ScanService` class
    - Implement `asyncio.Lock` to prevent concurrent scans (return 429 if locked)
    - Create `backend/routers/scan.py` with `POST /api/v1/resources/scan` route
    - Wire `ScanService` → `ResourceDetector` → scanners
    - Return `ScanResponse` on success (200), empty resources on no results (200)
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.8_

  - [x] 9.3 Implement global error handling
    - Create exception handlers in `backend/routers/` or `backend/main.py`
    - Map `AuthenticationError` → 401 with reason
    - Map `ScanInProgressError` → 429 with message
    - Map Pydantic `ValidationError` on output → 500 with generic message
    - Map unhandled exceptions → 500 with generic description and correlation ID (no stack traces, file paths, or class names)
    - _Requirements: 4.6, 4.7, 5.3, 7.5_

  - [ ]* 9.4 Write property test for error response sanitization
    - **Property 9: Error Response Sanitization**
    - **Validates: Requirements 4.7, 7.5**

- [x] 10. Wire application entry point
  - [x] 10.1 Create FastAPI application in `backend/main.py`
    - Instantiate FastAPI app
    - Include routers (health, scan)
    - Register middleware (correlation ID, request logging)
    - Load settings and wire dependency injection
    - Add startup validation: verify required dependencies importable, fail with error if not
    - Create `.env.example` file documenting all environment variables
    - _Requirements: 1.1, 1.5, 5.2_

- [ ] 11. Write integration tests
  - [ ]* 11.1 Write unit tests for health and scan endpoints
    - Test health endpoint returns 200 with correct shape
    - Test scan endpoint with mocked boto3 returns resources and summary
    - Test scan endpoint with no resources returns empty array and zero count
    - Test scan endpoint with invalid credentials returns 401
    - Test concurrent scan request returns 429
    - Test timeout returns partial results with `timed_out: true`
    - _Requirements: 1.3, 4.1, 4.2, 4.4, 4.5, 4.6, 4.8, 3.7_

  - [ ]* 11.2 Write integration tests for full scan flow
    - Test end-to-end scan with mocked boto3 through all layers
    - Test pagination with multi-page mocked responses
    - Test mixed failures: some scanners fail, others succeed
    - Test rate limiting: throttle responses trigger backoff
    - _Requirements: 3.4, 3.5, 3.6, 8.1, 8.3_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses `asyncio.to_thread()` with `ThreadPoolExecutor` for boto3 concurrency
- All scanners follow the `BaseScanner` interface for consistency and extensibility

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9"] },
    { "id": 5, "tasks": ["5.10", "5.11", "6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "8.1", "8.2", "8.3"] },
    { "id": 7, "tasks": ["8.4", "8.5", "8.6", "9.1", "9.2", "9.3"] },
    { "id": 8, "tasks": ["9.4", "10.1"] },
    { "id": 9, "tasks": ["11.1", "11.2"] }
  ]
}
```
