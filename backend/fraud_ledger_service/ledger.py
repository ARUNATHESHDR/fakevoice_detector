"""
Core hash-chain implementation -- the actual "blockchain" part.

This is a genuine append-only hash chain: each block includes the
previous block's hash, so altering any past block breaks every hash
after it. That's the real mechanism that makes this tamper-evident,
not a marketing label.

Honest scoping: this is a permissioned, simulated-multi-node ledger for
a hackathon demo -- NOT a production Hyperledger Fabric / Corda network.
It demonstrates the same trust model (append-only, replicated across
independent parties, cryptographically verifiable) without the multi-day
infrastructure project a real consortium chain would require. If this
goes to production, swap this module for actual Fabric/Corda -- nothing
above it (the API in main.py) needs to change, since the contract is
just "append a record, get back a verifiable chain."

CRITICAL PRIVACY RULE: never pass raw audio, voice embeddings, or any
biometric data into this ledger. Only hashes of alert METADATA (risk
score, rationale text, recommended action, timestamp, optionally a
hashed caller identifier) ever get chained. Biometric data is
irrevocable -- it must never live on an immutable, unerasable structure.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Block:
    index: int
    timestamp: float
    prev_hash: str
    data_hash: str          # hash of the alert record, never the raw record
    reporting_node: str      # which simulated institution submitted this
    hash: str = field(default="")

    def compute_hash(self) -> str:
        payload = f"{self.index}{self.timestamp}{self.prev_hash}{self.data_hash}{self.reporting_node}"
        return sha256_hex(payload)


class HashChain:
    """One institution's copy of the ledger. In a real consortium chain
    each institution runs its own node; here each HashChain instance
    plays that role."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.chain: list[Block] = [self._genesis_block()]

    def _genesis_block(self) -> Block:
        genesis = Block(index=0, timestamp=time.time(), prev_hash="0" * 64,
                         data_hash=sha256_hex("genesis"), reporting_node="system")
        genesis.hash = genesis.compute_hash()
        return genesis

    def latest_block(self) -> Block:
        return self.chain[-1]

    def append(self, data_hash: str, reporting_node: str) -> Block:
        prev = self.latest_block()
        block = Block(
            index=prev.index + 1,
            timestamp=time.time(),
            prev_hash=prev.hash,
            data_hash=data_hash,
            reporting_node=reporting_node,
        )
        block.hash = block.compute_hash()
        self.chain.append(block)
        return block

    def is_valid(self) -> tuple[bool, Optional[int]]:
        """Recomputes every block's hash and checks the prev_hash links.
        Returns (True, None) if intact, or (False, index) of the first
        block found to be tampered with."""
        for i in range(1, len(self.chain)):
            current, previous = self.chain[i], self.chain[i - 1]
            if current.prev_hash != previous.hash:
                return False, i
            if current.hash != current.compute_hash():
                return False, i
        return True, None

    def to_list(self) -> list[dict]:
        return [asdict(b) for b in self.chain]
