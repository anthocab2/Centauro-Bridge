"""One filtered frame feeds both the table and every plotted trace."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from centauro_atlas_bridge.reading.canonical import CanonicalDataset

COLUMNS = [
    "Fecha (UTC)",
    "Apertura",
    "Máximo",
    "Mínimo",
    "Cierre",
    "Volumen",
    "Activo",
    "Proveedor",
    "Ajustado",
    "Extracción",
    "Páginas",
]


def dataset_frame(
    dataset: CanonicalDataset, start: date | None = None, end: date | None = None
) -> pd.DataFrame:
    rows = [
        [
            bar.timestamp,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            dataset.request.ticker,
            dataset.provider,
            dataset.request.adjusted,
            dataset.extraction_id,
            ", ".join(map(str, bar.pages)),
        ]
        for bar in dataset.bars
        if (start is None or bar.timestamp.date() >= start)
        and (end is None or bar.timestamp.date() <= end)
    ]
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["Fecha (UTC)"] = pd.to_datetime(frame["Fecha (UTC)"], utc=True)
    return frame


def price_chart(frame: pd.DataFrame):
    chart = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.76, 0.24],
    )
    chart.add_trace(
        go.Candlestick(
            x=frame["Fecha (UTC)"].tolist(),
            open=frame["Apertura"].tolist(),
            high=frame["Máximo"].tolist(),
            low=frame["Mínimo"].tolist(),
            close=frame["Cierre"].tolist(),
            increasing_line_color="#147D73",
            decreasing_line_color="#CB5260",
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    chart.add_trace(
        go.Bar(
            x=frame["Fecha (UTC)"].tolist(),
            y=frame["Volumen"].tolist(),
            marker_color="#8BA7C4",
            name="Volumen",
        ),
        row=2,
        col=1,
    )
    chart.update_layout(
        height=460,
        margin={"l": 12, "r": 12, "t": 16, "b": 12},
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial", "color": "#334155"},
        xaxis_rangeslider_visible=False,
    )
    chart.update_yaxes(title_text="Precio", row=1, col=1, gridcolor="#E8EDF3")
    chart.update_yaxes(title_text="Volumen", row=2, col=1, gridcolor="#E8EDF3")
    chart.update_xaxes(title_text="Fecha · UTC", row=2, col=1)
    return chart
