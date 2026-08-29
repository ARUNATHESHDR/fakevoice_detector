"""
Fraud Intelligence Ledger service.

Purpose: when the alerting service fires a high-risk alert, this service
hashes the alert's metadata (never raw audio, never a voice embedding)
and appends it to a permissioned, hash-chained ledger -- replicated
across simulated "institution" nodes (a bank, a second bank, a telecom
operator). This directly answers two things the PS asks for:

  1. "A reusable security layer for telecom operators and enterprises"
     -- multiple institutions can check "has this caller/pattern been
     flagged before, by anyone in the consortium" without any one party
     owning or exposing their internal fraud database to the others.

  2. A tamper-evident audit trail -- if a bank's compliance team later
     needs to prove an alert record wasn't altered after the fact, the
     hash-chain makes any retroactive tampering mathematically
     detectable (see /ledger/verify).

Honest scoping: this simulates multi-node replication in one process
for the demo. A production deployment would run each node as a genuinely
separate service operated by a separate institution (e.g. on Hyperledger
Fabric) -- see ledger.py's docstring for what would change and what
wouldn't.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ledger import HashChain, sha256_hex

app = FastAPI(title="Fraud Intelligence Ledger")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simulated consortium: each of these is meant to represent a different
# institution's own copy of the ledger, replicated on every append.
NODE_IDS = ["bank_a", "bank_b", "telecom_x"]
nodes: dict[str, HashChain] = {node_id: HashChain(node_id) for node_id in NODE_IDS}

# index for fast lookup by hashed caller identifier -- never store the
# actual caller number, only a hash of it, alongside which block it's in
_caller_hash_index: dict[str, list[dict]] = {}


def _hash_alert_record(payload: dict) -> str:
    """Hashes only the fields relevant to a fraud record. Deliberately
    excludes anything that could be raw audio or biometric data --
    those fields are never even passed into this service to begin with,
    but this function only ever touches what IS passed."""
    relevant = {
        "session_id": payload.get("session_id"),
        "risk_score": payload.get("risk_score"),
        "rationale": payload.get("rationale"),
        "recommended_action": payload.get("recommended_action"),
        "caller_hash": payload.get("caller_hash"),  # pre-hashed by the caller, not raw
    }
    return sha256_hex(str(sorted(relevant.items())))


@app.post("/ledger/append")
async def append_alert(payload: dict):
    """
    payload:
    {
      "session_id": str, "risk_score": float, "rationale": str,
      "recommended_action": str,
      "caller_hash": optional str (SHA-256 of the caller's number,
                       computed by the CALLER of this endpoint -- this
                       service never sees or hashes a raw phone number),
      "reporting_node": optional str, defaults to "bank_a"
    }
    """
    data_hash = _hash_alert_record(payload)
    reporting_node = payload.get("reporting_node", NODE_IDS[0])

    # replicate the append across every simulated node in the consortium
    blocks = {}
    for node_id, chain in nodes.items():
        block = chain.append(data_hash, reporting_node)
        blocks[node_id] = block.hash

    if payload.get("caller_hash"):
        _caller_hash_index.setdefault(payload["caller_hash"], []).append({
            "block_hash": blocks[NODE_IDS[0]],
            "reporting_node": reporting_node,
            "risk_score": payload.get("risk_score"),
        })

    return {
        "status": "appended",
        "data_hash": data_hash,
        "block_hashes_by_node": blocks,
    }


@app.get("/ledger/query")
async def query_caller(caller_hash: str):
    """Lets any consortium member check: has this caller (identified only
    by a hash they compute themselves) been flagged before, by ANY
    institution in the consortium -- without seeing each other's raw
    fraud databases."""
    history = _caller_hash_index.get(caller_hash, [])
    return {
        "caller_hash": caller_hash,
        "prior_flags": len(history),
        "history": history,
    }


@app.get("/ledger/chain/{node_id}")
async def get_chain(node_id: str):
    if node_id not in nodes:
        return {"error": f"unknown node_id, must be one of {NODE_IDS}"}
    return {"node_id": node_id, "chain": nodes[node_id].to_list()}


@app.get("/ledger/verify/{node_id}")
async def verify_chain(node_id: str):
    """Demonstrates tamper-evidence: recomputes every block's hash and
    checks the prev_hash links. Use this in your demo to show that any
    attempt to retroactively edit a past alert breaks the chain."""
    if node_id not in nodes:
        return {"error": f"unknown node_id, must be one of {NODE_IDS}"}
    valid, bad_index = nodes[node_id].is_valid()
    return {"node_id": node_id, "valid": valid, "first_tampered_block": bad_index}


@app.get("/ledger/nodes")
async def list_nodes():
    return {"nodes": NODE_IDS, "chain_lengths": {n: len(c.chain) for n, c in nodes.items()}}


@app.get("/health")
def health():
    return {"status": "ok", "nodes": NODE_IDS}
