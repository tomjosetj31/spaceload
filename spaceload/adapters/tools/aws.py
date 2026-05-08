"""AWS CLI tool adapter for spaceload."""

from __future__ import annotations

import configparser
import logging
import os
import shutil
from pathlib import Path

from spaceload.adapters.tools.base import ToolAdapter

logger = logging.getLogger(__name__)

_AWS_CONFIG_PATH = Path.home() / ".aws" / "config"


class AWSAdapter(ToolAdapter):
    """Adapter for the AWS CLI: records the active profile and region.

    On replay, prints the export commands to activate the recorded profile,
    since environment variables cannot be set across process boundaries.
    """

    name = "aws"
    action_type = "aws_profile"

    def is_available(self) -> bool:
        """Return True if the aws CLI or ~/.aws/config is present."""
        return shutil.which("aws") is not None or _AWS_CONFIG_PATH.exists()

    def detect(self) -> dict | None:
        """Return the active AWS profile and region, or None if unavailable."""
        if not self.is_available():
            return None

        profile = (
            os.environ.get("AWS_PROFILE")
            or os.environ.get("AWS_DEFAULT_PROFILE")
        )
        region = (
            os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
        )

        # Fall back to reading the [default] section from ~/.aws/config
        if not profile and _AWS_CONFIG_PATH.exists():
            try:
                parser = configparser.ConfigParser()
                parser.read(_AWS_CONFIG_PATH)
                # AWS config sections look like "default" or "profile myprofile"
                if "default" in parser:
                    profile = "default"
                    if not region:
                        region = parser["default"].get("region")
            except Exception as exc:
                logger.debug("AWSAdapter.detect(): failed to read config: %s", exc)

        if not profile:
            return None

        return {
            "profile": profile,
            "region": region or None,
        }

    def apply(self, state: dict) -> bool:
        """Print the export commands needed to activate the recorded profile."""
        profile = state.get("profile", "")
        region = state.get("region")
        if not profile:
            return False
        # Replay is informational — env vars cannot be set in the parent shell
        print(f"         [ok] Recorded — to activate run:")
        print(f"              export AWS_PROFILE={profile}")
        if region:
            print(f"              export AWS_DEFAULT_REGION={region}")
        return True
