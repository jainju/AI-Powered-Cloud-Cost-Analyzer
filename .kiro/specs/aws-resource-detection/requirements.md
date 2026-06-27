# Requirements Document

## Introduction

This document defines the requirements for the AWS Resource Detection feature of the AI Cloud Cost Detective project. The feature provides a Python FastAPI backend (located in a `backend/` folder) that connects to an AWS account and detects all created resources across the account. This serves as the foundational data-gathering layer for cost analysis and optimization recommendations.

## Glossary

- **Backend**: The Python FastAPI application located in the `backend/` directory that exposes REST API endpoints for AWS resource detection.
- **Resource_Detector**: The service component responsible for discovering and cataloging AWS resources within an AWS account.
- **AWS_Client**: The component that authenticates and communicates with AWS APIs using boto3.
- **API_Server**: The FastAPI application server that handles incoming HTTP requests and returns responses.
- **Resource**: Any AWS service entity (e.g., EC2 instance, S3 bucket, RDS database, Lambda function) created in the target AWS account.
- **Resource_Inventory**: The structured collection of all detected AWS resources returned by the detection scan.
- **Service_Scanner**: A module responsible for scanning a specific AWS service type (e.g., EC2, S3, RDS) for resources.

## Requirements

### Requirement 1: Project Structure and FastAPI Application Setup

**User Story:** As a developer, I want a well-structured FastAPI backend in the `backend/` folder, so that I have a maintainable foundation for the AWS resource detection service.

#### Acceptance Criteria

1. THE Backend SHALL provide a FastAPI application entry point in `backend/main.py` that exposes a runnable ASGI application instance.
2. THE Backend SHALL include a `backend/requirements.txt` file listing all Python dependencies with exact pinned versions (using `==` operator).
3. THE API_Server SHALL expose a health check endpoint at `GET /health` that returns a 200 status code with a JSON body containing a `status` field set to `"healthy"` and a `service` field identifying the application name.
4. THE Backend SHALL organize code into modules: `routers/`, `services/`, `models/`, and `config/`, each containing an `__init__.py` file.
5. IF a required backend dependency is unavailable at startup, THEN THE Backend SHALL fail to start and output an error message indicating the missing dependency.

### Requirement 2: AWS Authentication and Connection

**User Story:** As a developer, I want the backend to securely connect to AWS, so that it can access resource information across the account.

#### Acceptance Criteria

1. THE AWS_Client SHALL authenticate using AWS credentials provided via environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`).
2. THE AWS_Client SHALL support an optional `AWS_SESSION_TOKEN` environment variable for temporary credentials.
3. IF AWS credentials are not configured, THEN THE AWS_Client SHALL return an error message indicating which required environment variable is missing.
4. IF AWS credentials are configured but invalid, THEN THE AWS_Client SHALL return an error message indicating the authentication failure reason returned by AWS.
5. THE AWS_Client SHALL validate AWS credentials by performing an API call to verify authentication before initiating a resource scan.
6. THE AWS_Client SHALL support specifying 1 to 30 AWS regions to scan via configuration.
7. IF a configured region name does not match a valid AWS region, THEN THE AWS_Client SHALL return an error message indicating the invalid region name.
8. IF an AWS API call fails due to insufficient permissions, THEN THE AWS_Client SHALL log the service name, attempted operation, and error message, and continue scanning other services.

### Requirement 3: Resource Detection Across AWS Services

**User Story:** As a user, I want the system to detect all resources in my AWS account, so that I have a complete inventory for cost analysis.

#### Acceptance Criteria

1. WHEN a resource scan is initiated, THE Resource_Detector SHALL scan for resources across the following AWS services: EC2 (instances, volumes, snapshots, elastic IPs), S3 (buckets), RDS (instances, clusters), Lambda (functions), DynamoDB (tables), ELB (load balancers), CloudFront (distributions), and IAM (users, roles).
2. WHEN a resource is detected, THE Resource_Detector SHALL capture the resource identifier, resource type, service name, region, creation date (when available), and the current state as reported by the AWS API for that resource type.
3. THE Resource_Detector SHALL scan all configured regions for regional services (EC2, RDS, Lambda, DynamoDB, ELB) and SHALL scan global services (S3, CloudFront, IAM) exactly once regardless of the number of configured regions.
4. WHEN scanning is complete, THE Resource_Detector SHALL return a Resource_Inventory containing all successfully detected resources grouped by service type, along with a list of any services that failed to scan.
5. IF a service scanner encounters an error for a specific service, THEN THE Resource_Detector SHALL log the service name, region, and error description, include the failed service in the Resource_Inventory's failure list, and continue scanning remaining services.
6. WHEN an AWS API returns paginated results, THE Resource_Detector SHALL retrieve all pages of results before marking that service-region scan as complete.
7. IF a resource scan exceeds 300 seconds of total elapsed time, THEN THE Resource_Detector SHALL terminate remaining scans and return a partial Resource_Inventory containing all resources detected up to that point along with an indication that the scan timed out.

### Requirement 4: Resource Detection API Endpoint

**User Story:** As a frontend client, I want an API endpoint to trigger resource detection and retrieve results, so that I can display the resource inventory to users.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `POST /api/v1/resources/scan` endpoint that initiates a full resource detection scan.
2. WHEN the scan endpoint is called, THE API_Server SHALL return a JSON response containing a `resources` array with the Resource_Inventory and a `summary` object within 300 seconds.
3. THE API_Server SHALL return each resource object in a consistent JSON schema including fields: `resource_id` (string), `resource_type` (string), `service` (string), `region` (string), `created_at` (ISO 8601 string or null), and `state` (string).
4. WHEN the scan is successful and resources are detected, THE API_Server SHALL return a 200 status code with the resource data.
5. WHEN the scan is successful and no resources are detected, THE API_Server SHALL return a 200 status code with an empty `resources` array and a `summary` showing zero total count.
6. IF the scan fails due to authentication errors, THEN THE API_Server SHALL return a 401 status code with an error message indicating the authentication failure reason.
7. IF the scan fails due to an unexpected error, THEN THE API_Server SHALL return a 500 status code with an error message indicating the nature of the failure without exposing internal implementation details.
8. IF the scan endpoint is called while a previous scan is already in progress, THEN THE API_Server SHALL return a 429 status code with an error message indicating that a scan is already running.

### Requirement 5: Response Models and Data Validation

**User Story:** As a developer, I want well-defined response models, so that API consumers can rely on a consistent data contract.

#### Acceptance Criteria

1. THE Backend SHALL define Pydantic models for all API request and response schemas, with each resource model including the fields: `resource_id` (string, required), `resource_type` (string, required), `service` (string, required), `region` (string, required), `created_at` (string or null, optional), and `state` (string, required).
2. THE API_Server SHALL validate all outgoing responses against the defined Pydantic models before returning them to the client.
3. IF response validation fails for an outgoing response, THEN THE API_Server SHALL return a 500 status code with an error message indicating a response serialization failure without exposing internal model details.
4. THE Backend SHALL include a summary object in the scan response containing: total resource count (integer), resource count per service (mapping of service name to integer count), and list of regions scanned (list of strings).
5. THE Backend SHALL represent fields that may be unavailable (such as `created_at`) as null in the JSON response rather than omitting the field.
6. FOR ALL valid Resource_Inventory objects, THE Backend SHALL ensure that serializing to JSON and deserializing back produces an object with identical field names, types, and values (field-by-field equality).

### Requirement 6: Configuration Management

**User Story:** As a developer, I want centralized configuration management, so that I can easily adjust settings without modifying code.

#### Acceptance Criteria

1. THE Backend SHALL load configuration from environment variables using a Pydantic Settings class.
2. THE Backend SHALL support a `.env` file for local development configuration, where environment variables take precedence over values defined in the `.env` file.
3. WHEN a required configuration value is missing, THE Backend SHALL fail to start with an error message that includes the name of each missing variable.
4. THE Backend SHALL provide configurable settings for: AWS regions to scan (list of valid AWS region identifiers, defaulting to `us-east-1`), API rate limiting parameters (maximum concurrent AWS API calls and maximum retry attempts), and log level (one of DEBUG, INFO, WARNING, ERROR, or CRITICAL, defaulting to INFO).
5. IF a configuration value is provided but invalid (unrecognized region identifier, non-positive integer for rate limiting parameters, or unsupported log level), THEN THE Backend SHALL fail to start with an error message indicating the invalid variable name and the accepted values.

### Requirement 7: Error Handling and Logging

**User Story:** As an operator, I want comprehensive logging and error handling, so that I can diagnose issues in production.

#### Acceptance Criteria

1. THE Backend SHALL use structured JSON logging for all log output, where each log entry includes at minimum: timestamp (ISO 8601 format), log level, correlation ID, and message.
2. WHEN an API request is received, THE API_Server SHALL log the request method, path, response status code, and response time in milliseconds.
3. WHEN an AWS API call fails, THE Resource_Detector SHALL log the service name, operation, error code, and error message at ERROR log level.
4. THE Backend SHALL generate a unique correlation ID per incoming API request and include it in all log entries produced during that request's processing.
5. IF an unhandled exception occurs, THEN THE API_Server SHALL return a JSON error response containing only an error field with a general description of the failure category and the correlation ID, without exposing stack traces, file paths, or internal service names.
6. THE Backend SHALL use the following log levels: ERROR for failures and exceptions, WARNING for retries and degraded operations, and INFO for request lifecycle events.

### Requirement 8: Rate Limiting and Throttling

**User Story:** As a developer, I want the backend to handle AWS API rate limits gracefully, so that scans complete reliably without being throttled.

#### Acceptance Criteria

1. WHEN an AWS API call is throttled, THE AWS_Client SHALL retry the call using exponential backoff starting with an initial delay of 1 second, a multiplier of 2, and a maximum delay cap of 30 seconds, up to a maximum of 3 retry attempts.
2. THE Resource_Detector SHALL limit concurrent AWS API calls to a maximum of 10 concurrent requests globally across all services being scanned.
3. IF all retry attempts are exhausted for an API call, THEN THE Resource_Detector SHALL log the failure including the service name, operation, error code, and number of attempts made, and continue scanning other resources while preserving any resources already detected.
