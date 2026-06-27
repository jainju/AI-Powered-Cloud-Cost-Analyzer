"""Pydantic models for detected AWS resources."""

from pydantic import BaseModel, ConfigDict
from typing import Optional


class DetectedResource(BaseModel):
    """Represents a single AWS resource detected during a scan.

    Fields:
        resource_id: The unique identifier for the resource (e.g., instance ID, bucket name).
        resource_type: The type of resource (e.g., 'instance', 'volume', 'bucket').
        service: The AWS service name (e.g., 'ec2', 's3', 'rds').
        region: The AWS region where the resource exists.
        created_at: ISO 8601 creation timestamp, or None if unavailable.
        state: The current state of the resource as reported by AWS.
    """

    model_config = ConfigDict(
        # Serialize None values as null rather than omitting the field
        ser_json_inf_nan="constants",
    )

    resource_id: str
    resource_type: str
    service: str
    region: str
    created_at: Optional[str] = None
    state: str

    def model_dump(self, **kwargs) -> dict:
        """Override to ensure created_at is always included even when None."""
        # By default Pydantic v2 includes None fields, but we explicitly
        # ensure exclude_none is not set to True
        kwargs.setdefault("exclude_none", False)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs) -> str:
        """Override to ensure created_at is always included even when None."""
        kwargs.setdefault("exclude_none", False)
        return super().model_dump_json(**kwargs)
