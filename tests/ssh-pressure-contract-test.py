"""Synthetic defensive scenarios; no network traffic, journal or host access."""

from pathlib import Path
import runpy
import unittest

api = runpy.run_path(str(Path(__file__).resolve().parents[1] / "decision/ssh-pressure.py"))
Policy, Window, assess = (api[name] for name in ("Policy", "Window", "assess"))
P = Policy(60, 15, 5, 2, 2)
WAVE = [Window(60, 20, 8, True), Window(120, 22, 9, False)]


class PressureContract(unittest.TestCase):
    def check(self, history, state, recommendation, as_of=None):
        got = assess(history, P, as_of=history[-1].end if as_of is None else as_of)
        self.assertEqual((got.state, got.recommendation), (state, recommendation))

    def test_quiet_and_legitimate_spike(self):
        self.check([Window(60, 0, 0, True)], "normal", "nenhuma")
        self.check([Window(60, 999, 0, True), Window(120, 999, 0, True)],
                   "pressao_a_verificar", "observar")

    def test_one_window_never_recommends_a_temporary_measure(self):
        self.check(WAVE[:1], "pressao_a_verificar", "observar")

    def test_sustained_pressure_and_service_impact(self):
        self.check(WAVE, "pressao_confirmada", "avaliar_medida_temporaria")
        self.check([WAVE[0], Window(120, 22, 9, True)], "pressao_confirmada", "investigar")

    def test_zero_alerts_with_lost_sensor_is_not_recovery(self):
        self.check(WAVE + [Window(180, None, 0, True)], "sem_visibilidade", "verificar_recolha")
        self.check(WAVE + [Window(180, 0, None, True)], "sem_visibilidade", "verificar_recolha")
        self.check(WAVE + [Window(180, 0, 0, None)], "sem_visibilidade", "verificar_recolha")

    def test_low_counts_and_unresponsive_service_are_not_recovery(self):
        self.check(WAVE + [Window(180, 0, 0, False)], "incidente_em_observacao", "investigar")
        self.check([Window(60, 0, 0, False)], "ssh_sem_resposta", "verificar_servico")

    def test_recovery_requires_consecutive_healthy_windows(self):
        first = WAVE + [Window(180, 0, 0, True)]
        self.check(first, "em_recuperacao", "manter_observacao")
        self.check(first + [Window(300, 0, 0, True)], "em_recuperacao", "manter_observacao")
        recovered = first + [Window(240, 0, 0, True)]
        self.check(recovered, "recuperado", "rever_medida_temporaria")
        self.check(recovered + [Window(300, 0, 0, True)], "normal", "nenhuma")

    def test_gap_breaks_pressure_streak(self):
        self.check([WAVE[0], Window(180, 22, 9, True)], "pressao_a_verificar", "observar")

    def test_stale_or_empty_is_not_normal(self):
        self.check(WAVE, "sem_visibilidade", "verificar_recolha", as_of=180)
        self.check([], "sem_visibilidade", "verificar_recolha", as_of=180)

    def test_bad_input_is_rejected(self):
        for values in [(None, None, None, None), (60, True, 0, True), (60, -1, 0, True),
                       (60, 0, 0, 1)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                Window(*values)
        cases = [(WAVE[::-1], 120), ([WAVE[0], WAVE[0]], 120),
                 ([Window(61, 0, 0, True)], 120), (WAVE, 100)]
        for history, as_of in cases:
            with self.subTest(history=history, as_of=as_of), self.assertRaises(ValueError):
                assess(history, P, as_of=as_of)


if __name__ == "__main__":
    unittest.main(verbosity=2)
