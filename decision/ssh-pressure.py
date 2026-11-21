"""Offline, advisory-only SSH pressure decisions. No I/O or privileged operations."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Policy:
    window_seconds: int
    new_connections: int
    rejected_auth: int
    pressure_windows: int
    recovery_windows: int

    def __post_init__(self):
        for value in vars(self).values():
            if type(value) is not int or value <= 0:
                raise ValueError("policy values must be positive integers")


@dataclass(frozen=True)
class Window:
    end: int
    # None means unavailable or untrusted; 0 means a measured zero.
    connections: int | None
    rejected_auth: int | None
    ssh_responds: bool | None

    def __post_init__(self):
        if type(self.end) is not int or self.end < 0:
            raise ValueError("window end must be a non-negative integer")
        for value in (self.connections, self.rejected_auth):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("window counts must be non-negative integers or unknown")
        if self.ssh_responds is not None and type(self.ssh_responds) is not bool:
            raise ValueError("availability must be Boolean or unknown")


@dataclass(frozen=True)
class Decision:
    state: str
    recommendation: str


def assess(windows: Iterable[Window], policy: Policy, *, as_of: int) -> Decision:
    """Replay aligned, closed windows of one SSH service and assess at epoch as_of."""
    if type(as_of) is not int or as_of < 0:
        raise ValueError("as_of must be a non-negative integer")
    previous = None
    incident = False
    pressure = calm = 0
    result = Decision("sem_visibilidade", "verificar_recolha")
    for window in windows:
        if (window.end < policy.window_seconds or window.end > as_of
                or window.end % policy.window_seconds):
            raise ValueError("window end must be aligned and closed")
        if previous is not None and window.end <= previous:
            raise ValueError("window ends must be strictly increasing")
        if previous is not None and window.end - previous != policy.window_seconds:
            pressure = calm = 0
        previous = window.end
        if window.connections is None or window.rejected_auth is None or window.ssh_responds is None:
            pressure = calm = 0
            result = Decision("sem_visibilidade", "verificar_recolha")
            continue

        high_net = window.connections >= policy.new_connections
        high_auth = window.rejected_auth >= policy.rejected_auth
        responds = window.ssh_responds

        if high_net and high_auth:
            pressure += 1
        else:
            pressure = 0
        if pressure >= policy.pressure_windows:
            incident = True

        if incident:
            # A low count alone is not recovery. The legitimate path must work.
            if not high_net and not high_auth and responds:
                calm += 1
                if calm >= policy.recovery_windows:
                    result = Decision("recuperado", "rever_medida_temporaria")
                    incident = False
                    calm = 0
                else:
                    result = Decision("em_recuperacao", "manter_observacao")
            else:
                calm = 0
                result = Decision(
                    "pressao_confirmada" if pressure >= policy.pressure_windows else "incidente_em_observacao",
                    "avaliar_medida_temporaria" if not responds and pressure >= policy.pressure_windows
                    else "investigar",
                )
        elif not responds:
            result = Decision("ssh_sem_resposta", "verificar_servico")
        elif high_net or high_auth:
            result = Decision("pressao_a_verificar", "observar")
        else:
            result = Decision("normal", "nenhuma")

    if previous is None or as_of - previous >= policy.window_seconds:
        return Decision("sem_visibilidade", "verificar_recolha")
    return result
