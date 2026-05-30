"""Shared Temporal client connection — self-hosted server, no TLS.

Reads:
  TEMPORAL_ADDRESS    default localhost:7233
  TEMPORAL_NAMESPACE  default "default"
"""
from __future__ import annotations

import os

from temporalio.client import Client


async def connect() -> Client:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    return await Client.connect(address, namespace=namespace)
