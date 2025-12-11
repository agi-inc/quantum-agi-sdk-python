"""
Cloud inference server components
"""

from quantum_agi_sdk.cloud.server import create_app
from quantum_agi_sdk.cloud.mcp_server import mcp as mcp_server

__all__ = ["create_app", "mcp_server"]
