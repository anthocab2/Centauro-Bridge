"""Spanish local dashboard. Reruns only read; submissions are explicit session actions."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import streamlit as st

from centauro_atlas_bridge.application.connections import probe_atlas, probe_massive
from centauro_atlas_bridge.application.coordinator import Coordinator
from centauro_atlas_bridge.application.models import InputError, Profile, Request
from centauro_atlas_bridge.application.state import ACTIVE
from centauro_atlas_bridge.reading.canonical import ReadingError, read_extraction

from .demo import demo_dataset
from .presentation import dataset_frame, price_chart
from .session import DashboardSession, diagnostic_text

STATES = {
    "preparing": "Preparando",
    "executing": "En ejecución",
    "verifying": "Verificando",
    "verified": "Verificada",
    "failed": "Fallida",
    "interrupted": "Interrumpida",
}
MODES = {
    "new": "Extracción nueva",
    "resumed": "Reanudación",
    "reused": "Reutilización",
    "recovered": "Recuperación",
}
PHASES = {
    "pending": "Pendiente",
    "running": "En curso",
    "completed": "Completado",
    "failed": "Fallido",
    "interrupted": "Interrumpido",
    "unknown": "Desconocido",
    "partial_or_unknown": "Parcial o desconocido",
    "not_verified": "Sin verificar",
    "invalid": "Inválida",
    "verified": "Verificada",
}


def create_coordinator(state_dir=None):
    return Coordinator(state_dir)


def show_diagnostic(code):
    message, action = diagnostic_text(code)
    st.error(message)
    st.caption(f"Siguiente acción: {action}")


def profile_view(session, core, jobs):
    st.title("Conexiones")
    st.write(
        "Configure el perfil que usará cada extracción. Las credenciales permanecen en esta sesión local."
    )
    active = any(job["state"] in ACTIVE for job in jobs)
    if active:
        st.info(
            "Hay un trabajo activo. El perfil podrá cambiarse cuando termine; puede consultar su estado en Extracciones."
        )
    with st.form("profile_form"):
        st.subheader("Perfil de trabajo")
        left, right = st.columns(2)
        profile_id = left.text_input("Nombre del perfil", value="mvp", disabled=active)
        target = right.text_input(
            "Alias del destino Atlas", value="atlas-mvp", disabled=active
        )
        database = left.text_input(
            "Base de datos", value="centauro_bridge_mvp", disabled=active
        )
        plan = right.text_input(
            "Plan declarado de Massive",
            value="unknown",
            help="Una etiqueta declarada por usted; no implica capacidad comprobada.",
            disabled=active,
        )
        api_key = st.text_input(
            "Credencial de Massive",
            type="password",
            key="massive_credential",
            disabled=active,
        )
        uri = st.text_input(
            "URI de MongoDB Atlas",
            type="password",
            key="atlas_credential",
            disabled=active,
        )
        saved = st.form_submit_button(
            "Activar perfil en esta sesión", type="primary", disabled=active
        )
    if saved:
        try:
            profile = Profile(
                profile_id, target, database, api_key, uri, declared_plan=plan
            )
            session.configure(profile, core)
            for key in ("atlas_probe", "massive_probe", "dataset", "dataset_demo"):
                st.session_state.pop(key, None)
            st.success(
                "Perfil con formato válido. Las conexiones y permisos aún no están comprobados."
            )
        except InputError:
            st.error(
                "No se pudo activar el perfil. Revise los nombres, la URI, la credencial y que no haya un trabajo activo."
            )
    if session.profile is None:
        st.caption("Activar un perfil no inicia extracciones ni prueba servicios.")
        return
    profile = session.profile
    st.divider()
    st.subheader("Evidencia de conexión")
    st.caption(
        f"Perfil activo: {profile.profile_id} · Massive → {profile.destination_id} / {profile.database} · Plan declarado: {profile.declared_plan}"
    )
    first, second = st.columns(2)
    with first, st.container(border=True):
        st.markdown("**MongoDB Atlas**")
        st.write("Comprueba únicamente que Atlas responda al ping.")
        if st.button("Comprobar ping de Atlas", disabled=active):
            with st.spinner("Comprobando Atlas…"):
                st.session_state.atlas_probe = probe_atlas(profile)
        evidence = st.session_state.get("atlas_probe")
        if evidence and evidence["status"] == "confirmed":
            st.success("Conexión comprobada mediante ping.")
            st.caption(
                f"{evidence['checked_at']} · Permisos de lectura y escritura: desconocidos."
            )
        elif evidence:
            show_diagnostic(evidence.get("diagnostic", {}).get("code"))
        else:
            st.caption("Conexión: sin comprobar. Escritura: desconocida.")
    with second, st.container(border=True):
        st.markdown("**Massive**")
        st.write("Una petición de un día, límite 1, sin paginación ni almacenamiento.")
        with st.form("probe_form"):
            ticker = st.text_input("Activo de prueba", value="AAPL", disabled=active)
            day = st.date_input(
                "Día de prueba",
                value=datetime.now(UTC).date() - timedelta(days=1),
                disabled=active,
            )
            probe = st.form_submit_button("Comprobar esta operación", disabled=active)
        if probe:
            try:
                request = Request(ticker.upper(), day.isoformat(), day.isoformat())
                with st.spinner("Comprobando la solicitud acotada…"):
                    st.session_state.massive_probe = probe_massive(profile, request)
            except InputError:
                st.error("Revise el activo y la fecha de la prueba.")
        evidence = st.session_state.get("massive_probe")
        if evidence and evidence["status"] == "confirmed":
            st.success("Capacidad comprobada sólo para la operación mostrada.")
            st.caption(
                f"{evidence['request']['ticker']} · {evidence['request']['start_date']} · Ajustado: sí · Plan exacto: desconocido."
            )
            if evidence["data_status"] == "empty":
                st.info("Respuesta válida sin resultados para ese día.")
        elif evidence:
            show_diagnostic(evidence.get("diagnostic", {}).get("code"))
        else:
            st.caption(
                "Capacidad: desconocida. El formato válido no prueba acceso al proveedor."
            )


def job_details(job):
    st.subheader("Detalle del trabajo")
    a, b, c = st.columns(3)
    a.metric("Estado", STATES.get(job["state"], "Desconocido"))
    b.metric("Tipo de ejecución", MODES.get(job.get("mode"), "Por determinar"))
    c.metric("Destino", job["profile"]["destination_id"])
    st.caption(f"Job ID: {job['job_id']}")
    st.caption(f"Extracción: {job['extraction_id']}")
    request = job["request"]
    st.write(
        f"**{request['ticker']}** · {request['start_date']} → {request['end_date']} · Ajustado: {'sí' if request['adjusted'] else 'no'} · Proveedor: {job['profile']['provider']}"
    )
    cols = st.columns(3)
    for column, key, title in zip(
        cols,
        ("execution_status", "storage_status", "verification_status"),
        ("Ejecución", "Almacenamiento", "Verificación"),
        strict=True,
    ):
        column.markdown(f"**{title}**  \n{PHASES.get(job[key], 'Desconocido')}")
    st.caption(
        f"Creado: {job['created_at']} · Actualizado: {job['updated_at']} · Finalizado: {job['finished_at'] or '—'} · Fechas UTC"
    )
    if job.get("resumed_from"):
        st.caption(f"Reanuda el trabajo: {job['resumed_from']}")
    if job.get("diagnostic"):
        show_diagnostic(job["diagnostic"]["code"])
    elif job["state"] == "verified":
        st.success(
            "El trabajo terminó con verificación satisfactoria. Abra Datos para comprobar y leer su contenido actual en Atlas."
        )
    else:
        st.info(
            "El trabajo continúa de forma independiente. Actualizar esta página sólo consulta su estado."
        )
    with st.expander("Solicitud y trazabilidad"):
        st.json(
            {
                "solicitud": request,
                "perfil": job["profile"],
                "transiciones": job["events"],
                "capacidad_observada": job.get("capability"),
                "conteo_historico_core": (job.get("result") or {}).get("bar_count"),
            }
        )


def extraction_view(session, core, jobs):
    st.title("Extracciones")
    st.write(
        "Inicie una solicitud y siga su ejecución. Un único trabajo puede estar activo en esta instalación."
    )
    if st.button("Actualizar estado", icon=":material/refresh:"):
        jobs = session.refresh(core)
    if session.unknown_pending:
        show_diagnostic("worker_start_unknown")
        if st.button("Consultar estado tras inicio incierto"):
            jobs = session.reconcile_unknown(core)
            st.info(
                "Estado consultado. Revise los trabajos antes de preparar otro intento."
            )
    active = any(job["state"] in ACTIVE for job in jobs)
    spent = session.nonce in session.used
    if (
        spent
        and not active
        and st.button(
            "Preparar otra solicitud",
            disabled=session.unknown_pending and not session.unknown_checked,
        )
    ):
        session.prepare_another(core)
        st.rerun()
    with st.expander("Nueva extracción", expanded=not active and not spent):
        if session.profile is None:
            st.info("Configure un perfil en Conexiones para habilitar el envío.")
        disabled = session.profile is None or active or spent or session.unknown_pending
        token = session.nonce
        with st.form("extraction_form"):
            cols = st.columns([1, 1, 1])
            ticker = cols[0].text_input("Activo", value="AAPL", disabled=disabled)
            start = cols[1].date_input(
                "Fecha inicial",
                value=datetime.now(UTC).date() - timedelta(days=7),
                disabled=disabled,
            )
            end = cols[2].date_input(
                "Fecha final",
                value=datetime.now(UTC).date() - timedelta(days=1),
                disabled=disabled,
            )
            adjusted = st.checkbox("Precios ajustados", value=True, disabled=disabled)
            submitted = st.form_submit_button(
                "Iniciar extracción", type="primary", disabled=disabled
            )
        if submitted:
            try:
                request = Request(
                    ticker.upper(), start.isoformat(), end.isoformat(), adjusted
                )
                with st.spinner("Solicitando un trabajador al core…"):
                    session.submit(core, token, request=request)
                st.rerun()
            except InputError:
                st.error("Revise el activo, las fechas y el perfil antes de enviar.")
    if session.receipt:
        status = session.receipt.get("status")
        if status == "busy":
            st.info("Instalación ocupada. Consulte el trabajo activo.")
        elif status == "accepted":
            st.caption(
                "Solicitud aceptada por el core; esto no implica que la extracción haya terminado."
            )
        elif not session.unknown_pending:
            show_diagnostic(session.receipt.get("diagnostic", {}).get("code"))
    if not jobs:
        st.info(
            "Aún no hay trabajos guardados. Las solicitudes aparecerán aquí incluso después de actualizar la interfaz."
        )
        return
    ids = [job["job_id"] for job in jobs]
    index = ids.index(session.selected_job_id) if session.selected_job_id in ids else 0
    selected = st.selectbox(
        "Trabajo guardado",
        ids,
        index=index,
        format_func=lambda value: (
            f"{value[:12]} · {STATES.get(next(job['state'] for job in jobs if job['job_id'] == value), 'Desconocido')}"
        ),
    )
    session.selected_job_id = selected
    job = next(job for job in jobs if job["job_id"] == selected)
    job_details(job)
    if job["state"] in {"failed", "interrupted"}:
        can_resume = (
            session.profile is not None
            and session.profile.public() == job["profile"]
            and not active
            and not spent
            and not session.unknown_pending
        )
        if st.button("Reanudar con un nuevo trabajo", disabled=not can_resume):
            session.submit(core, session.nonce, resume_id=selected)
            st.rerun()
        if not can_resume:
            st.caption(
                "Para reanudar, active el perfil original y prepare otra solicitud cuando la instalación esté libre."
            )


def render_dataset(dataset, demo):
    if demo:
        st.warning(
            "DATOS DE PRUEBA · Serie sintética DEMO. No corresponde a cotizaciones reales ni demuestra conexión a Massive o Atlas."
        )
    request = dataset.request
    st.subheader(f"{request.ticker} · Barras diarias")
    st.caption(
        f"Solicitado: {request.start_date} → {request.end_date} · Proveedor: {dataset.provider} · Ajustado: {'sí' if request.adjusted else 'no'}"
    )
    cols = st.columns(4)
    cols[0].metric("Barras reconstruidas", dataset.bar_count)
    cols[1].metric("Páginas canónicas", len(dataset.captures))
    cols[2].metric("Duplicados exactos", dataset.exact_duplicates)
    cols[3].metric("Integridad al abrir", "Verificada")
    st.caption(
        f"Lectura: {dataset.read_at} · Conteo del lector; el resultado histórico del core conserva bar_count=null."
    )
    if not dataset.bars:
        st.caption(
            f"Extracción: {dataset.extraction_id} · Referencia de lectura: {dataset.snapshot_id}"
        )
        with st.expander("Capturas canónicas de la extracción vacía"):
            st.json([asdict(capture) for capture in dataset.captures])
        st.info(
            "Extracción vacía válida: no hay barras que mostrar. No se rellenaron intervalos."
        )
        return
    observed_start, observed_end = (
        dataset.bars[0].timestamp.date(),
        dataset.bars[-1].timestamp.date(),
    )
    st.caption(
        f"Periodo observado: {dataset.bars[0].timestamp.isoformat()} → {dataset.bars[-1].timestamp.isoformat()}"
    )
    with st.container(border=True):
        left, right = st.columns(2)
        filter_start = left.date_input(
            "Mostrar desde (UTC)",
            value=observed_start,
            min_value=observed_start,
            max_value=observed_end,
            key=f"from_{dataset.snapshot_id}",
        )
        filter_end = right.date_input(
            "Mostrar hasta (UTC)",
            value=observed_end,
            min_value=observed_start,
            max_value=observed_end,
            key=f"to_{dataset.snapshot_id}",
        )
        if filter_end < filter_start:
            st.error("El final del filtro debe ser igual o posterior al inicio.")
            return
        frame = dataset_frame(dataset, filter_start, filter_end)
        st.caption(
            f"{len(frame)} barras visibles · Mismos filtros para tabla y gráfico · Zona horaria UTC"
        )
        st.plotly_chart(price_chart(frame), width="stretch", key="ohlcv_chart")
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
            column_config={
                "Extracción": None,
                "Proveedor": None,
                "Activo": None,
                "Ajustado": None,
            },
        )
    with st.expander("Referencia y capturas canónicas"):
        st.write(f"Extracción: `{dataset.extraction_id}`")
        st.caption(f"Referencia de lectura: {dataset.snapshot_id}")
        st.json([asdict(capture) for capture in dataset.captures])


def data_view(session, core, jobs):
    st.title("Datos")
    st.write(
        "Abra una extracción y compruebe su evidencia canónica antes de explorar las barras OHLCV."
    )
    if st.session_state.get("dataset_demo"):
        if st.button("Salir del ejemplo local"):
            st.session_state.pop("dataset", None)
            st.session_state.dataset_demo = False
            st.rerun()
        render_dataset(st.session_state.dataset, True)
        return
    available = [
        job for job in jobs if job.get("extraction_id") and job["state"] not in ACTIVE
    ]
    if not available:
        st.info(
            "No hay extracciones terminadas para abrir. Puede explorar el ejemplo local identificado como datos de prueba."
        )
        return
    ids = [job["job_id"] for job in available]
    selected = st.selectbox(
        "Extracción guardada",
        ids,
        format_func=lambda value: (
            f"{next(job['request']['ticker'] for job in available if job['job_id'] == value)} · {value[:12]}"
        ),
    )
    job = next(job for job in available if job["job_id"] == selected)
    if st.session_state.get("dataset_job") != selected:
        st.session_state.pop("dataset", None)
    matches = session.profile is not None and session.profile.public() == job["profile"]
    active = any(item["state"] in ACTIVE for item in jobs)
    if not matches:
        st.info(
            "Active el perfil y destino originales en Conexiones para abrir esta extracción."
        )
    if st.button(
        "Verificar y abrir datos", type="primary", disabled=not matches or active
    ):
        st.session_state.pop("dataset", None)
        try:
            with st.spinner("Leyendo y verificando las páginas canónicas…"):
                dataset = read_extraction(session.profile, job)
            st.session_state.dataset = dataset
            st.session_state.dataset_job = selected
        except ReadingError as error:
            show_diagnostic(error.code)
    dataset = st.session_state.get("dataset")
    if (
        dataset is not None
        and matches
        and st.session_state.get("dataset_job") == selected
    ):
        render_dataset(dataset, False)


def main(state_dir=None):
    st.set_page_config(page_title="Centauro Bridge", page_icon="◈", layout="wide")
    st.markdown(
        """<style>
    .block-container {padding-top: 2.5rem; max-width: 1280px;}
    h1 {letter-spacing: -0.035em; font-weight: 650;}
    h2, h3 {letter-spacing: -0.02em;}
    [data-testid="stSidebar"] {border-right: 1px solid #e5eaf0;}
    [data-testid="stMetricValue"] {font-size: 1.65rem;}
    </style>""",
        unsafe_allow_html=True,
    )
    if "dashboard_session" not in st.session_state:
        st.session_state.dashboard_session = DashboardSession()
    if st.session_state.pop("demo_navigation", False):
        st.session_state.section = "Datos"
    session = st.session_state.dashboard_session
    try:
        core = create_coordinator(state_dir)
        jobs = session.refresh(core)
        with st.sidebar:
            st.markdown("### ◈ Centauro Bridge")
            st.caption("MASSIVE → ATLAS  /  LOCAL")
            st.divider()
            section = st.radio(
                "Navegación", ["Conexiones", "Extracciones", "Datos"], key="section"
            )
            st.divider()
            st.caption("PERFIL ACTIVO")
            st.write(
                session.profile.profile_id if session.profile else "Sin configurar"
            )
            active = next((job for job in jobs if job["state"] in ACTIVE), None)
            st.caption("TRABAJADOR")
            st.write(STATES[active["state"]] if active else "Sin trabajo activo")
            st.divider()
            if st.button("Explorar datos de prueba", width="stretch"):
                st.session_state.dataset = demo_dataset()
                st.session_state.dataset_demo = True
                # Radio already exists; navigate on the next rerun via a pending value.
                st.session_state.demo_navigation = True
                st.rerun()
            st.caption("Ejemplo sintético, sin credenciales ni conexiones.")
            st.caption("Estado local estable · HBT-CEN-002")
        if section == "Conexiones":
            profile_view(session, core, jobs)
        elif section == "Extracciones":
            extraction_view(session, core, jobs)
        else:
            data_view(session, core, jobs)
    except Exception:  # noqa: BLE001 -- UI must not render traceback or credential-bearing exception
        st.error(
            "No se pudo completar la operación local. Revise la configuración y consulte los trabajos antes de reintentar."
        )
