"""
hiveai/dbc — Decentralized Brain Collective

Phase 1: Chain Protocol (CPU-only)
  chain.py          — Hive blockchain abstraction, pair encoding, protocol logic
  hivepoa.py        — Adapter storage (IPFS now, HivePoA later)
  node.py           — Node daemon: watch chain, verify, update
  compute_client.py — HivePoA GPU Compute Marketplace REST client
"""

from hiveai.dbc.chain import (
    ChainState,
    ResilientChain,
    decode_pair,
    encode_pair,
    pre_submission_check,
    scan_for_secrets,
)
from hiveai.dbc.hivepoa import HivePoAClient
from hiveai.dbc.node import DBCNode, NodeConfig
from hiveai.dbc.compute_client import HivePoAComputeClient

__all__ = [
    "ChainState",
    "ResilientChain",
    "encode_pair",
    "decode_pair",
    "scan_for_secrets",
    "pre_submission_check",
    "HivePoAClient",
    "HivePoAComputeClient",
    "DBCNode",
    "NodeConfig",
]
