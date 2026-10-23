"""Acceptance tests for real Massive pagination recovery flow."""

from types import SimpleNamespace

from scripts import real_massive_pagination_test as script


class FakeCursor:
    """Minimal MongoDB cursor."""

    def __init__(self, documents):
        self.documents = list(
            documents
        )

    def sort(
        self,
        field,
        direction,
    ):
        del direction

        self.documents.sort(
            key=lambda document: (
                document.get(
                    field,
                    0,
                )
            )
        )

        return self

    def __iter__(self):
        return iter(
            self.documents
        )


class FakeLedgerCollection:
    """Minimal ledger collection."""

    def __init__(self, documents):
        self.documents = documents

    def find(
        self,
        query,
        projection=None,
    ):
        del projection

        extraction_id = query.get(
            "extraction_id"
        )

        return FakeCursor(
            [
                document
                for document in self.documents
                if document.get(
                    "extraction_id"
                )
                == extraction_id
            ]
        )


class FakeRawCollection:
    """Minimal raw collection."""

    def __init__(self, count):
        self.count = count

    def count_documents(
        self,
        query,
    ):
        del query

        return self.count


class FakeDatabase:
    """Minimal database wrapper."""

    def __init__(
        self,
        ledger_documents,
        raw_count,
    ):
        self.collections = {
            script.PAGE_LEDGER_COLLECTION:
                FakeLedgerCollection(
                    ledger_documents
                ),
            script.RAW_COLLECTION:
                FakeRawCollection(
                    raw_count
                ),
        }

    def __getitem__(
        self,
        name,
    ):
        return self.collections[
            name
        ]


class FakeClient:
    """Minimal Atlas client."""

    def __init__(
        self,
        database,
    ):
        self.database = database

    def __getitem__(
        self,
        name,
    ):
        del name

        return self.database

    def close(
        self,
    ):
        return None


def test_existing_progress_counts_only_checkpointed_records(
    monkeypatch,
):
    """A ledger-ahead page must not be counted before replay."""
    database = FakeDatabase(
        ledger_documents=[
            {
                "extraction_id":
                    "recovery-test",
                "page_number":
                    1,
                "canonical_record_count":
                    1000,
            },
            {
                "extraction_id":
                    "recovery-test",
                "page_number":
                    2,
                "canonical_record_count":
                    1000,
            },
        ],
        raw_count=2,
    )

    monkeypatch.setattr(
        script,
        "create_atlas_client",
        lambda: FakeClient(
            database
        ),
    )

    monkeypatch.setattr(
        script,
        "get_database_name",
        lambda: "centauro_test",
    )

    (
        ledger_pages,
        total_records,
        raw_documents,
    ) = script.load_existing_progress(
        extraction_id=(
            "recovery-test"
        ),
        record_through_page=1,
    )

    assert ledger_pages == 2
    assert total_records == 1000
    assert raw_documents == 2


def test_prepare_resume_accepts_one_page_ahead(
    monkeypatch,
):
    """Checkpoint N and verified page N+1 require safe replay."""
    cursor = (
        "https://api.massive.com/"
        "v3/reference/tickers?cursor=page2"
    )

    monkeypatch.setattr(
        script,
        "get_checkpoint",
        lambda **kwargs: {
            "cursor":
                cursor,
            "metadata": {
                "completed":
                    False,
                "last_page":
                    1,
            },
        },
    )

    monkeypatch.setattr(
        script,
        "validate_massive_url",
        lambda url: None,
    )

    monkeypatch.setattr(
        script,
        "reconcile_equivalent_raw_captures",
        lambda extraction_id: 1,
    )

    monkeypatch.setattr(
        script,
        "verify_extraction",
        lambda extraction_id: {
            "verification_errors": [
                "execution_not_completed",
            ],
            "ledger_page_numbers": [
                1,
                2,
            ],
            "canonical_page_numbers": [
                1,
                2,
            ],
        },
    )

    progress_calls = []

    def fake_load_existing_progress(
        extraction_id,
        record_through_page=None,
    ):
        progress_calls.append(
            (
                extraction_id,
                record_through_page,
            )
        )

        return (
            2,
            1000,
            2,
        )

    monkeypatch.setattr(
        script,
        "load_existing_progress",
        fake_load_existing_progress,
    )

    result = script.prepare_resume(
        "recovery-test"
    )

    assert result == (
        cursor,
        1,
        1000,
        2,
        "replay_required",
        1,
    )

    assert progress_calls == [
        (
            "recovery-test",
            1,
        )
    ]


def test_replay_same_content_advances_and_does_not_double_count(
    monkeypatch,
):
    """Safe replay counts page N+1 exactly once and continues."""
    page_two_url = (
        "https://api.massive.com/"
        "v3/reference/tickers?cursor=page2"
    )

    page_three_url = (
        "https://api.massive.com/"
        "v3/reference/tickers?cursor=page3"
    )

    page_two_payload = {
        "results": [
            {
                "ticker":
                    f"TICKER{index:04d}",
            }
            for index in range(
                1000
            )
        ],
        "next_url":
            page_three_url,
    }

    page_three_payload = {
        "results": [
            {
                "ticker":
                    f"FINAL{index:04d}",
            }
            for index in range(
                250
            )
        ],
    }

    responses = [
        page_two_payload,
        page_three_payload,
    ]

    stored_pages = []
    checkpoints = []
    completed_runs = []
    final_results = []

    monkeypatch.setattr(
        script,
        "parse_arguments",
        lambda: SimpleNamespace(
            resume="recovery-test"
        ),
    )

    monkeypatch.setattr(
        script,
        "get_massive_api_key",
        lambda: "test-key",
    )

    monkeypatch.setattr(
        script,
        "prepare_resume",
        lambda extraction_id: (
            page_two_url,
            1,
            1000,
            2,
            "replay_required",
            1,
        ),
    )

    monkeypatch.setattr(
        script,
        "start_run",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        script,
        "fail_run",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        script,
        "validate_massive_url",
        lambda url: None,
    )

    monkeypatch.setattr(
        script,
        "validate_massive_payload",
        lambda payload: None,
    )

    monkeypatch.setattr(
        script,
        "sanitize_payload_for_storage",
        lambda payload: payload,
    )

    def fake_fetch_json(
        url,
        **kwargs,
    ):
        del url
        del kwargs

        return responses.pop(
            0
        )

    monkeypatch.setattr(
        script,
        "fetch_json",
        fake_fetch_json,
    )

    def fake_store_raw_payload_chunks(
        **kwargs,
    ):
        page_number = kwargs[
            "pagination"
        ][
            "page_number"
        ]

        stored_pages.append(
            page_number
        )

        return [
            f"document-{page_number}"
        ]

    monkeypatch.setattr(
        script,
        "store_raw_payload_chunks",
        fake_store_raw_payload_chunks,
    )

    def fake_register_canonical_page(
        **kwargs,
    ):
        return {
            "canonical_content_hash":
                kwargs[
                    "content_hash"
                ],
            "canonical_document_ids": [
                (
                    "canonical-"
                    f"{kwargs['page_number']}"
                )
            ],
        }

    monkeypatch.setattr(
        script,
        "register_canonical_page",
        fake_register_canonical_page,
    )

    def fake_save_checkpoint(
        **kwargs,
    ):
        checkpoints.append(
            {
                "cursor":
                    kwargs[
                        "cursor"
                    ],
                "metadata":
                    kwargs[
                        "metadata"
                    ],
            }
        )

    monkeypatch.setattr(
        script,
        "save_checkpoint",
        fake_save_checkpoint,
    )

    def fake_complete_run(
        **kwargs,
    ):
        completed_runs.append(
            kwargs
        )

    monkeypatch.setattr(
        script,
        "complete_run",
        fake_complete_run,
    )

    monkeypatch.setattr(
        script,
        "load_existing_progress",
        lambda extraction_id: (
            3,
            2250,
            3,
        ),
    )

    def fake_print_final_result(
        **kwargs,
    ):
        final_results.append(
            kwargs
        )

    monkeypatch.setattr(
        script,
        "print_final_result",
        fake_print_final_result,
    )

    script.main()

    assert responses == []

    assert stored_pages == [
        2,
        3,
    ]

    assert checkpoints == [
        {
            "cursor":
                page_three_url,
            "metadata": {
                "completed":
                    False,
                "last_page":
                    2,
            },
        },
        {
            "cursor":
                None,
            "metadata": {
                "completed":
                    True,
                "last_page":
                    3,
            },
        },
    ]

    assert completed_runs == [
        {
            "extraction_id":
                "recovery-test",
            "pages_stored":
                3,
        }
    ]

    assert final_results == [
        {
            "extraction_id":
                "recovery-test",
            "pages_stored":
                3,
            "total_results":
                2250,
            "total_raw_documents":
                3,
        }
    ]
