# Backend services

Eight containers, one per responsibility. All contracts are defined in
`shared/schemas.py` — copy that file's shapes into any service you modify,
and if you need to change a shape, tell the whole team before doing it.

## Data flow

```
frontend (mic)
  -> edge_ingestion  (WebSocket :8001)   VAD + windowing
    -> gateway       (:8000)             fans out in parallel:
        -> spectral_service    (:8002)
        -> prosody_service     (:8003)
        -> consistency_service (:8004)
      -> fusion_engine (:8005)           combines 3 scores + context
    -> alerting_service (:8006)          pushes score_update / alert over WS
        -> fraud_ledger_service (:8007)  hashes + chains high-risk alerts
                                          across 3 simulated institutions
  -> frontend (dashboard)
```

## Ports

| Service | Port | Protocol |
|---|---|---|
| gateway | 8000 | REST |
| edge_ingestion | 8001 | WebSocket |
| spectral_service | 8002 | REST (internal) |
| prosody_service | 8003 | REST (internal) |
| consistency_service | 8004 | REST (internal) |
| fusion_engine | 8005 | REST (internal) |
| alerting_service | 8006 | REST + WebSocket |
| fraud_ledger_service | 8007 | REST |
| frontend | 3000 | HTTP |

## fraud_ledger_service — the blockchain component

Only reached when `alert_triggered=True` (i.e. sustained high risk, not
every window). `alerting_service` calls it fire-and-forget — if the
ledger is down, the actual alert (WebSocket/SMS/email) still goes out;
recording to the ledger never blocks or breaks the primary alert path.

Key endpoints:
- `POST /ledger/append` — called internally by alerting_service
- `GET /ledger/query?caller_hash=...` — cross-institution lookup: has
  this caller (identified only by a hash the caller computes themselves,
  never a raw phone number) been flagged before by any node
- `GET /ledger/chain/{node_id}` — dump one institution's full chain
  (`node_id` is one of `bank_a`, `bank_b`, `telecom_x`)
- `GET /ledger/verify/{node_id}` — recomputes every block's hash and
  checks the chain links; use this to demo tamper-evidence

See `fraud_ledger_service/ledger.py` for the actual hash-chain mechanism
and its honest scoping notes (simulated multi-node, not a production
Hyperledger Fabric/Corda deployment).

## Running a single service on its own (outside Docker)

Useful while you're actively developing just one piece:

```bash
cd backend/spectral_service
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8002
```

Repeat the same pattern for any other service, changing the port to match
the table above. Each service only needs its own model file(s) to be
useful; the others can stay untrained placeholders while you test.

On Windows, `setup.bat` / `run.bat` / `stop.bat` in the project root do
this for all 8 services at once — see the top-level README.

## Health checks

Every service exposes `GET /health` — useful for confirming a container
(or, in native mode, a terminal window) started correctly before you
debug further upstream.
