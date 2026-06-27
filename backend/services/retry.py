"""Retry logic with exponential backoff for AWS API calls.

Implements retry behavior for throttled AWS API calls using exponential
backoff with configurable initial delay, multiplier, and maximum delay cap.
Only ThrottlingException and RequestLimitExceeded errors trigger retries.
"""

import asyncio
import functools
import logging
from typing import Callable, Set

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# AWS error codes that trigger retry behavior
RETRYABLE_ERROR_CODES: Set[str] = {"ThrottlingException", "RequestLimitExceeded"}

# Backoff configuration constants
INITIAL_DELAY_SECONDS: float = 1.0
BACKOFF_MULTIPLIER: int = 2
MAX_DELAY_SECONDS: float = 30.0


def calculate_backoff_delay(attempt: int) -> float:
    """Calculate the backoff delay for a given retry attempt number.

    Uses exponential backoff formula: min(initial_delay * multiplier^(attempt-1), max_delay)

    Args:
        attempt: The retry attempt number (1-based).

    Returns:
        The delay in seconds before the next retry.
    """
    delay = INITIAL_DELAY_SECONDS * (BACKOFF_MULTIPLIER ** (attempt - 1))
    return min(delay, MAX_DELAY_SECONDS)


def is_retryable_error(error: ClientError) -> bool:
    """Check if a ClientError is a retryable throttling error.

    Args:
        error: The botocore ClientError to check.

    Returns:
        True if the error code is in the set of retryable error codes.
    """
    error_code = error.response.get("Error", {}).get("Code", "")
    return error_code in RETRYABLE_ERROR_CODES


def retry_with_backoff(
    service: str,
    operation: str,
    max_attempts: int = 3,
):
    """Decorator that adds retry logic with exponential backoff to async functions.

    Only retries on ThrottlingException and RequestLimitExceeded errors.
    Other errors are raised immediately without retry.

    Args:
        service: The AWS service name (for logging).
        operation: The API operation name (for logging).
        max_attempts: Maximum number of total attempts (initial + retries).

    Returns:
        Decorated async function with retry behavior.
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except ClientError as e:
                    if not is_retryable_error(e):
                        raise

                    last_exception = e
                    error_code = e.response.get("Error", {}).get("Code", "")

                    if attempt < max_attempts:
                        delay = calculate_backoff_delay(attempt)
                        logger.warning(
                            "Throttled by AWS API. Retrying.",
                            extra={
                                "service": service,
                                "operation": operation,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                                "error_code": error_code,
                                "delay_seconds": delay,
                            },
                        )
                        await asyncio.sleep(delay)
                    else:
                        # All retries exhausted
                        error_message = e.response.get("Error", {}).get(
                            "Message", str(e)
                        )
                        logger.error(
                            "All retry attempts exhausted for AWS API call.",
                            extra={
                                "service": service,
                                "operation": operation,
                                "error_code": error_code,
                                "error_message": error_message,
                                "attempts_made": max_attempts,
                            },
                        )
                        raise

            # This should not be reached, but just in case
            raise last_exception  # pragma: no cover

        return wrapper

    return decorator


async def retry_aws_call(
    func: Callable,
    service: str,
    operation: str,
    max_attempts: int = 3,
    *args,
    **kwargs,
):
    """Execute an AWS API call with retry logic and exponential backoff.

    This is a functional alternative to the decorator for cases where
    decorating is not practical.

    Only retries on ThrottlingException and RequestLimitExceeded errors.
    Other errors are raised immediately without retry.

    Args:
        func: The callable to execute (can be sync or async).
        service: The AWS service name (for logging).
        operation: The API operation name (for logging).
        max_attempts: Maximum number of total attempts (initial + retries).
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the successful function call.

    Raises:
        ClientError: If all retry attempts are exhausted or a non-retryable error occurs.
    """
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except ClientError as e:
            if not is_retryable_error(e):
                raise

            last_exception = e
            error_code = e.response.get("Error", {}).get("Code", "")

            if attempt < max_attempts:
                delay = calculate_backoff_delay(attempt)
                logger.warning(
                    "Throttled by AWS API. Retrying.",
                    extra={
                        "service": service,
                        "operation": operation,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error_code": error_code,
                        "delay_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)
            else:
                # All retries exhausted
                error_message = e.response.get("Error", {}).get("Message", str(e))
                logger.error(
                    "All retry attempts exhausted for AWS API call.",
                    extra={
                        "service": service,
                        "operation": operation,
                        "error_code": error_code,
                        "error_message": error_message,
                        "attempts_made": max_attempts,
                    },
                )
                raise

    # This should not be reached, but just in case
    raise last_exception  # pragma: no cover
