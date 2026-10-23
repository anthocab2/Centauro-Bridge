"""Thin Massive/Atlas adapter: the legacy extractor remains the sole raw writer."""

from .diagnostics import VerificationFailed
from .models import Request


class MassiveAtlasAdapter:
    def extraction_id(self, request: Request) -> str:
        # Imported only in the worker, after explicit environment configuration.
        from centauro_atlas_bridge.sources.massive import build_extraction_id

        return build_extraction_id(**request.public())

    def execute(self, request: Request, progress) -> dict:
        from centauro_atlas_bridge.ingestion.checkpoints import get_checkpoint
        from centauro_atlas_bridge.ingestion.runs import get_run
        from centauro_atlas_bridge.ingestion.verification import verify_extraction
        from centauro_atlas_bridge.sources.massive import extract_daily_aggs

        extraction_id = self.extraction_id(request)
        endpoint = (
            f"/v2/aggs/ticker/{request.ticker}/range/1/day/"
            f"{request.start_date}/{request.end_date}"
        )
        checkpoint = get_checkpoint("massive", endpoint, extraction_id)
        previous_run = get_run(extraction_id)
        if checkpoint and checkpoint.get("metadata", {}).get("completed"):
            mode = (
                "reused"
                if previous_run and previous_run.get("status") == "completed"
                else "recovered"
            )
        elif checkpoint or previous_run:
            mode = "resumed"
        else:
            mode = "new"
        progress(state="executing", execution_status="running", mode=mode)
        # Return value is raw document IDs, not bars or necessarily new writes.
        # [] is a valid successful completed-checkpoint reuse/recovery.
        extract_daily_aggs(**request.public())
        progress(
            state="verifying",
            execution_status="completed",
            storage_status="completed",
            verification_status="running",
        )
        verification = verify_extraction(extraction_id)
        if verification.get("verified") is not True:
            progress(verification_status="invalid")
            raise VerificationFailed
        total = verification.get("total_results")
        # The verifier can prove emptiness. A canonical analytical bar reader is future work.
        data_status = "empty" if type(total) is int and total == 0 else "unknown"
        if type(total) is int and total > 0:
            data_status = "present"
        return {
            "mode": mode,
            "verified": True,
            "data_status": data_status,
            "bar_count": None,
            "observed_pages": (
                verification.get("observed_pages")
                if type(verification.get("observed_pages")) is int
                else None
            ),
            "capability": {
                "status": "confirmed" if mode in {"new", "resumed"} else "unknown",
                "scope": "requested_daily_aggregates"
                if mode in {"new", "resumed"}
                else None,
                "exact_plan": "unknown",
            },
        }
