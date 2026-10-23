"""Session-only presentation actions. All job lifecycle operations delegate to Core."""

from dataclasses import dataclass, field
from uuid import uuid4

from centauro_atlas_bridge.application.coordinator import Coordinator
from centauro_atlas_bridge.application.models import InputError, Profile, Request
from centauro_atlas_bridge.application.state import ACTIVE


@dataclass
class DashboardSession:
    profile: Profile | None = field(default=None, repr=False)
    receipt: dict | None = None
    selected_job_id: str | None = None
    nonce: str = field(default_factory=lambda: uuid4().hex)
    used: set[str] = field(default_factory=set)
    unknown_pending: bool = False
    unknown_checked: bool = False

    def public(self):
        return {
            "profile": self.profile.public() if self.profile else None,
            "receipt": self.receipt,
            "selected_job_id": self.selected_job_id,
        }

    def refresh(self, coordinator: Coordinator) -> list[dict]:
        return coordinator.state.status()

    def configure(self, profile: Profile, coordinator: Coordinator):
        if any(job["state"] in ACTIVE for job in self.refresh(coordinator)):
            raise InputError(
                "Espere a que termine el trabajo activo para cambiar el perfil."
            )
        self.profile = profile

    def submit(
        self,
        coordinator: Coordinator,
        token: str,
        request: Request | None = None,
        resume_id: str | None = None,
    ):
        if token != self.nonce or token in self.used or self.unknown_pending:
            return self.receipt
        if self.profile is None:
            raise InputError("Configure un perfil antes de iniciar una extracción.")
        if (request is None) == (resume_id is None):
            raise InputError("Seleccione una solicitud o un trabajo para reanudar.")
        self.used.add(token)  # Never rearm automatically on a rerun or completion.
        self.receipt = (
            coordinator.resume(resume_id, self.profile)
            if resume_id
            else coordinator.start(self.profile, request)
        )
        self.selected_job_id = self.receipt.get("job_id") or self.selected_job_id
        self.unknown_pending = (
            self.receipt.get("diagnostic", {}).get("code") == "worker_start_unknown"
        )
        self.unknown_checked = False
        if self.unknown_pending:
            self.refresh(coordinator)  # Mandatory reconciliation before another offer.
        return self.receipt

    def reconcile_unknown(self, coordinator: Coordinator):
        jobs = self.refresh(coordinator)
        self.unknown_checked = True
        return jobs

    def prepare_another(self, coordinator: Coordinator):
        jobs = self.refresh(coordinator)
        if any(job["state"] in ACTIVE for job in jobs):
            raise InputError("Hay un trabajo activo; consulte su estado.")
        if self.unknown_pending and not self.unknown_checked:
            raise InputError(
                "Consulte el estado del inicio incierto antes de volver a intentarlo."
            )
        self.nonce = uuid4().hex
        self.unknown_pending = False
        self.unknown_checked = False
        self.receipt = None


DIAGNOSTICS = {
    "credentials": (
        "Credenciales rechazadas.",
        "Revise la credencial de la conexión y vuelva a probarla.",
    ),
    "access_restricted": (
        "Acceso restringido para esta operación.",
        "Revise los permisos y la ventana de fechas permitida.",
    ),
    "rate_limited": (
        "Límite temporal de solicitudes.",
        "Espere antes de volver a intentar la misma solicitud.",
    ),
    "connection": (
        "No se pudo establecer la conexión.",
        "Revise la red y la disponibilidad del servicio.",
    ),
    "worker_interrupted": (
        "El trabajador se interrumpió.",
        "Revise el destino y reanude desde el checkpoint.",
    ),
    "worker_start_unknown": (
        "No se recibió confirmación del trabajador.",
        "Consulte el estado antes de preparar otro intento.",
    ),
    "verification_failed": (
        "La evidencia almacenada no pasó la verificación.",
        "Investigue la integridad; no utilice estos datos como válidos.",
    ),
    "selection_mismatch": (
        "El perfil o la solicitud no corresponden a esta extracción.",
        "Configure el perfil y destino originales.",
    ),
    "provenance_mismatch": (
        "La procedencia de Atlas no coincide con la solicitud.",
        "Revise la extracción seleccionada; no mezcle destinos.",
    ),
    "invalid_evidence": (
        "La lectura detectó evidencia inválida o en conflicto.",
        "Revise hashes, ledger y estado de la extracción en Atlas.",
    ),
    "missing_fragment": (
        "Falta un fragmento canónico.",
        "Complete o recupere la ingesta antes de abrir los datos.",
    ),
    "bar_conflict": (
        "Hay valores incompatibles para una misma barra.",
        "Investigue las páginas implicadas; no se mezclaron sus valores.",
    ),
    "invalid_bar": (
        "Una barra tiene campos OHLCV inválidos.",
        "Revise el contenido original de la extracción.",
    ),
    "evidence_changed": (
        "La evidencia cambió durante la lectura.",
        "Espere a que termine la actividad y vuelva a verificar.",
    ),
    "read_failed": (
        "No se pudo leer la extracción en Atlas.",
        "Compruebe la conexión y los permisos de lectura.",
    ),
    "provider_response": (
        "La respuesta del proveedor no confirmó la operación.",
        "Revise el acceso a la operación solicitada.",
    ),
}


def diagnostic_text(code: str) -> tuple[str, str]:
    return DIAGNOSTICS.get(
        code,
        (
            "No se pudo completar la operación.",
            "Revise la configuración y consulte el estado antes de reintentar.",
        ),
    )
