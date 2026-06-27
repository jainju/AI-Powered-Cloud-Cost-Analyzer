"""Unit tests for retry logic with exponential backoff."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from backend.services.retry import (
    INITIAL_DELAY_SECONDS,
    BACKOFF_MULTIPLIER,
    MAX_DELAY_SECONDS,
    RETRYABLE_ERROR_CODES,
    calculate_backoff_delay,
    is_retryable_error,
    retry_aws_call,
    retry_with_backoff,
)


def make_client_error(error_code: str, message: str = "Test error") -> ClientError:
    """Helper to create a botocore ClientError with given code and message."""
    return ClientError(
        error_response={"Error": {"Code": error_code, "Message": message}},
        operation_name="TestOperation",
    )


class TestCalculateBackoffDelay:
    """Tests for the calculate_backoff_delay function."""

    def test_first_attempt_returns_initial_delay(self):
        assert calculate_backoff_delay(1) == 1.0

    def test_second_attempt_doubles_delay(self):
        assert calculate_backoff_delay(2) == 2.0

    def test_third_attempt_quadruples_delay(self):
        assert calculate_backoff_delay(3) == 4.0

    def test_fourth_attempt_eight_seconds(self):
        assert calculate_backoff_delay(4) == 8.0

    def test_delay_caps_at_max(self):
        # 2^5 = 32, capped at 30
        assert calculate_backoff_delay(6) == 30.0

    def test_large_attempt_still_capped(self):
        assert calculate_backoff_delay(100) == 30.0

    def test_formula_matches_spec(self):
        """Verify formula: min(1 * 2^(N-1), 30) for attempts 1 through 5."""
        expected = [1.0, 2.0, 4.0, 8.0, 16.0]
        for attempt, expected_delay in enumerate(expected, start=1):
            assert calculate_backoff_delay(attempt) == expected_delay


class TestIsRetryableError:
    """Tests for the is_retryable_error function."""

    def test_throttling_exception_is_retryable(self):
        error = make_client_error("ThrottlingException")
        assert is_retryable_error(error) is True

    def test_request_limit_exceeded_is_retryable(self):
        error = make_client_error("RequestLimitExceeded")
        assert is_retryable_error(error) is True

    def test_access_denied_is_not_retryable(self):
        error = make_client_error("AccessDeniedException")
        assert is_retryable_error(error) is False

    def test_resource_not_found_is_not_retryable(self):
        error = make_client_error("ResourceNotFoundException")
        assert is_retryable_error(error) is False

    def test_unknown_error_is_not_retryable(self):
        error = make_client_error("SomeUnknownError")
        assert is_retryable_error(error) is False


class TestRetryWithBackoffDecorator:
    """Tests for the retry_with_backoff decorator."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Function succeeds on first call without retries."""

        @retry_with_backoff(service="ec2", operation="describe_instances", max_attempts=3)
        async def succeed():
            return "success"

        result = await succeed()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_throttling(self):
        """Function retries on ThrottlingException and succeeds."""
        call_count = 0

        @retry_with_backoff(service="ec2", operation="describe_instances", max_attempts=3)
        async def throttle_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise make_client_error("ThrottlingException")
            return "success"

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await throttle_then_succeed()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_request_limit_exceeded(self):
        """Function retries on RequestLimitExceeded."""
        call_count = 0

        @retry_with_backoff(service="s3", operation="list_buckets", max_attempts=3)
        async def limit_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise make_client_error("RequestLimitExceeded")
            return "done"

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await limit_then_succeed()

        assert result == "done"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_raises_immediately_on_non_retryable_error(self):
        """Non-retryable errors are raised immediately without retry."""
        call_count = 0

        @retry_with_backoff(service="ec2", operation="describe_instances", max_attempts=3)
        async def access_denied():
            nonlocal call_count
            call_count += 1
            raise make_client_error("AccessDeniedException")

        with pytest.raises(ClientError) as exc_info:
            await access_denied()

        assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts_exhausted(self):
        """Raises the last error after all retry attempts are exhausted."""

        @retry_with_backoff(service="rds", operation="describe_db_instances", max_attempts=3)
        async def always_throttle():
            raise make_client_error("ThrottlingException", "Rate exceeded")

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ClientError) as exc_info:
                await always_throttle()

        assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"

    @pytest.mark.asyncio
    async def test_backoff_delays_are_correct(self):
        """Verifies that sleep is called with correct exponential delays."""
        call_count = 0

        @retry_with_backoff(service="ec2", operation="describe_instances", max_attempts=4)
        async def always_throttle():
            nonlocal call_count
            call_count += 1
            raise make_client_error("ThrottlingException")

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ClientError):
                await always_throttle()

        # With 4 max_attempts, there are 3 retries (attempts 1, 2, 3 trigger sleeps)
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(1.0)  # attempt 1: 1 * 2^0 = 1
        mock_sleep.assert_any_call(2.0)  # attempt 2: 1 * 2^1 = 2
        mock_sleep.assert_any_call(4.0)  # attempt 3: 1 * 2^2 = 4

    @pytest.mark.asyncio
    async def test_logs_warning_on_each_retry(self, caplog):
        """Each retry logs a WARNING with service, operation, and attempt."""
        call_count = 0

        @retry_with_backoff(service="lambda", operation="list_functions", max_attempts=3)
        async def throttle_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise make_client_error("ThrottlingException")
            return "ok"

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock):
            with caplog.at_level(logging.WARNING, logger="backend.services.retry"):
                await throttle_twice()

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 2

        # Verify extra fields on the first warning
        assert warning_records[0].service == "lambda"
        assert warning_records[0].operation == "list_functions"
        assert warning_records[0].attempt == 1

    @pytest.mark.asyncio
    async def test_logs_error_on_final_failure(self, caplog):
        """Final failure after all retries logs at ERROR level."""

        @retry_with_backoff(service="dynamodb", operation="list_tables", max_attempts=2)
        async def always_throttle():
            raise make_client_error("ThrottlingException", "Too many requests")

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock):
            with caplog.at_level(logging.ERROR, logger="backend.services.retry"):
                with pytest.raises(ClientError):
                    await always_throttle()

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert error_records[0].service == "dynamodb"
        assert error_records[0].operation == "list_tables"
        assert error_records[0].attempts_made == 2


class TestRetryAwsCall:
    """Tests for the retry_aws_call utility function."""

    @pytest.mark.asyncio
    async def test_success_with_sync_function(self):
        """Works with a synchronous callable."""
        mock_fn = MagicMock(return_value="result")

        result = await retry_aws_call(
            mock_fn, service="ec2", operation="describe_instances", max_attempts=3
        )

        assert result == "result"
        assert mock_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_success_with_async_function(self):
        """Works with an async callable."""
        mock_fn = AsyncMock(return_value="async_result")

        result = await retry_aws_call(
            mock_fn, service="s3", operation="list_buckets", max_attempts=3
        )

        assert result == "async_result"
        assert mock_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_throttled_sync_function(self):
        """Retries a sync function that raises ThrottlingException."""
        mock_fn = MagicMock(
            side_effect=[
                make_client_error("ThrottlingException"),
                "success",
            ]
        )

        with patch("backend.services.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_aws_call(
                mock_fn, service="ec2", operation="describe_instances", max_attempts=3
            )

        assert result == "success"
        assert mock_fn.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_non_retryable_error_immediately(self):
        """Non-retryable errors raise immediately without retry."""
        mock_fn = MagicMock(side_effect=make_client_error("AccessDeniedException"))

        with pytest.raises(ClientError) as exc_info:
            await retry_aws_call(
                mock_fn, service="ec2", operation="describe_instances", max_attempts=3
            )

        assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"
        assert mock_fn.call_count == 1
