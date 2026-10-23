"""Unit tests for canonical source-page ledger behavior."""

from copy import deepcopy

from centauro_atlas_bridge.ingestion import page_ledger


class FakeCollection:
    """Minimal in-memory MongoDB collection."""

    def __init__(self):
        self.document = None

    def create_index(
        self,
        fields,
        unique=False,
    ):
        return "fake_index"

    def find_one_and_update(
        self,
        identity,
        update,
        upsert=False,
        return_document=None,
    ):
        if self.document is None:
            if not upsert:
                return None

            self.document = {
                **identity,
                **update.get(
                    "$setOnInsert",
                    {},
                ),
            }

        for key, value in update.get(
            "$set",
            {},
        ).items():
            self.document[
                key
            ] = value

        for key, value in update.get(
            "$inc",
            {},
        ).items():
            self.document[
                key
            ] = (
                self.document.get(
                    key,
                    0,
                )
                + value
            )

        for key, value in update.get(
            "$addToSet",
            {},
        ).items():
            values = self.document.setdefault(
                key,
                [],
            )

            if value not in values:
                values.append(
                    value
                )

        return deepcopy(
            self.document
        )


class FakeDatabase:
    """Minimal fake database."""

    def __init__(
        self,
        collection,
    ):
        self.collection = collection

    def __getitem__(
        self,
        name,
    ):
        return self.collection


class FakeClient:
    """Minimal fake MongoDB client."""

    def __init__(
        self,
        collection,
    ):
        self.collection = collection

    def __getitem__(
        self,
        name,
    ):
        return FakeDatabase(
            self.collection
        )

    def close(
        self,
    ):
        pass


def install_fake_atlas(
    monkeypatch,
):
    """Install one in-memory ledger collection."""
    collection = (
        FakeCollection()
    )

    monkeypatch.setattr(
        page_ledger,
        "create_atlas_client",
        lambda: FakeClient(
            collection
        ),
    )

    monkeypatch.setattr(
        page_ledger,
        "get_database_name",
        lambda: "test_database",
    )

    return collection


def test_page_content_hash_ignores_transport_metadata():
    """Different request IDs must not change logical record identity."""
    first = {
        "status": "OK",
        "request_id": "AAA",
        "results": [
            {
                "c": 100,
            }
        ],
    }

    second = {
        "status": "OK",
        "request_id": "BBB",
        "results": [
            {
                "c": 100,
            }
        ],
    }

    assert (
        page_ledger.calculate_page_content_hash(
            first
        )
        == page_ledger.calculate_page_content_hash(
            second
        )
    )


def test_changed_results_change_content_hash():
    """Different source records must produce a different content hash."""
    first = {
        "results": [
            {
                "c": 100,
            }
        ],
    }

    second = {
        "results": [
            {
                "c": 101,
            }
        ],
    }

    assert (
        page_ledger.calculate_page_content_hash(
            first
        )
        != page_ledger.calculate_page_content_hash(
            second
        )
    )


def test_first_capture_remains_canonical_across_retry(
    monkeypatch,
):
    """Changed metadata must not replace the first canonical capture."""
    install_fake_atlas(
        monkeypatch
    )

    first = (
        page_ledger.register_canonical_page(
            source="massive",
            endpoint="/test",
            extraction_id="extract_1",
            page_number=1,
            payload_hash="payload_A",
            content_hash="content_same",
            document_ids=[
                "document_A",
            ],
            record_count=1,
        )
    )

    second = (
        page_ledger.register_canonical_page(
            source="massive",
            endpoint="/test",
            extraction_id="extract_1",
            page_number=1,
            payload_hash="payload_B",
            content_hash="content_same",
            document_ids=[
                "document_B",
            ],
            record_count=1,
        )
    )

    assert (
        first[
            "canonical_payload_hash"
        ]
        == "payload_A"
    )

    assert (
        second[
            "canonical_payload_hash"
        ]
        == "payload_A"
    )

    assert (
        second[
            "canonical_document_ids"
        ]
        == [
            "document_A"
        ]
    )

    assert (
        second[
            "capture_count"
        ]
        == 2
    )

    assert set(
        second[
            "observed_payload_hashes"
        ]
    ) == {
        "payload_A",
        "payload_B",
    }

    assert (
        second[
            "observed_content_hashes"
        ]
        == [
            "content_same"
        ]
    )


def test_different_page_content_is_recorded_as_conflict(
    monkeypatch,
):
    """Ledger must preserve evidence when a retry changes source data."""
    install_fake_atlas(
        monkeypatch
    )

    page_ledger.register_canonical_page(
        source="massive",
        endpoint="/test",
        extraction_id="extract_1",
        page_number=1,
        payload_hash="payload_A",
        content_hash="content_A",
        document_ids=[
            "document_A",
        ],
        record_count=1,
    )

    second = (
        page_ledger.register_canonical_page(
            source="massive",
            endpoint="/test",
            extraction_id="extract_1",
            page_number=1,
            payload_hash="payload_B",
            content_hash="content_B",
            document_ids=[
                "document_B",
            ],
            record_count=1,
        )
    )

    assert (
        second[
            "canonical_content_hash"
        ]
        == "content_A"
    )

    assert set(
        second[
            "observed_content_hashes"
        ]
    ) == {
        "content_A",
        "content_B",
    }
