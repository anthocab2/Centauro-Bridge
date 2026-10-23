from datetime import date

from centauro_atlas_bridge.dashboard.demo import demo_dataset
from centauro_atlas_bridge.dashboard.presentation import dataset_frame, price_chart


def test_table_and_chart_share_exact_filtered_dataset():
    dataset = demo_dataset()
    frame = dataset_frame(dataset, date(2026, 10, 5), date(2026, 10, 9))
    chart = price_chart(frame)
    assert len(frame) == 5
    assert list(chart.data[0].x) == list(frame["Fecha (UTC)"])
    assert list(chart.data[1].x) == list(frame["Fecha (UTC)"])
    for name, column in [
        ("open", "Apertura"),
        ("high", "Máximo"),
        ("low", "Mínimo"),
        ("close", "Cierre"),
    ]:
        assert list(getattr(chart.data[0], name)) == list(frame[column])
    assert list(chart.data[1].y) == list(frame["Volumen"])
    assert set(frame["Extracción"]) == {dataset.extraction_id}
    assert set(frame["Activo"]) == {"DEMO"}


def test_filter_without_bars_does_not_fill_gaps():
    frame = dataset_frame(demo_dataset(), date(2026, 10, 3), date(2026, 10, 4))
    assert frame.empty
    assert len(price_chart(frame).data[0].x) == 0
