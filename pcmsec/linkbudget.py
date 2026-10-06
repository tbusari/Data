"""Link-budget arithmetic used in the paper, so every number is reproducible.

All quantities in dB / dBm / dBi.  ``fspl`` is free-space path loss.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

C = 299_792_458.0
BOLTZMANN_DBM_HZ = -173.98  # kT at 290 K in dBm/Hz (10*log10(1.380649e-23*290) + 30)


def fspl_db(distance_m: float, freq_hz: float) -> float:
    return 20 * math.log10(4 * math.pi * distance_m * freq_hz / C)


def distance_for_fspl(fspl: float, freq_hz: float) -> float:
    return 10 ** (fspl / 20) * C / (4 * math.pi * freq_hz)


def equivalent_path_loss(distance_m: float, freq_hz: float, pad_db: float) -> float:
    """A fixed attenuator adds to free-space loss; EPL maps a short path to a long one."""
    return fspl_db(distance_m, freq_hz) + pad_db


@dataclass
class LinkBudget:
    tx_power_dbm: float = 36.99        # 5 W
    tx_losses_db: float = 1.0
    tx_gain_dbi: float = -1.0
    rx_gain_dbi: float = 6.5
    rx_cable_loss_db: float = 1.5
    freq_hz: float = 2.2505e9
    bit_rate: float = 3.2768e6
    noise_figure_db: float = 3.5
    if_bandwidth_hz: float = 3.3e6
    required_ebn0_db: float = 9.5      # multi-symbol PCM/FM, LS-28 class detector
    coding_gain_db: float = 0.0        # e.g. LDPC if the installed option set supports it

    @property
    def eirp_dbm(self) -> float:
        return self.tx_power_dbm - self.tx_losses_db + self.tx_gain_dbi

    def received_power_dbm(self, path_loss_db: float, polarization_loss_db: float = 0.0) -> float:
        return self.eirp_dbm - path_loss_db + self.rx_gain_dbi - self.rx_cable_loss_db - polarization_loss_db

    @property
    def noise_floor_dbm(self) -> float:
        return BOLTZMANN_DBM_HZ + 10 * math.log10(self.if_bandwidth_hz) + self.noise_figure_db

    @property
    def threshold_dbm(self) -> float:
        """Receiver sensitivity: noise floor + required Eb/N0 scaled to the IF bandwidth, less coding gain."""
        ebn0_to_snr = 10 * math.log10(self.bit_rate / self.if_bandwidth_hz)
        return self.noise_floor_dbm + self.required_ebn0_db + ebn0_to_snr - self.coding_gain_db

    def margin_db(self, path_loss_db: float, polarization_loss_db: float = 0.0) -> float:
        return self.received_power_dbm(path_loss_db, polarization_loss_db) - self.threshold_dbm

    def rx_gain_for_margin(self, path_loss_db: float, margin_db: float, polarization_loss_db: float = 0.0) -> float:
        return margin_db + self.threshold_dbm - (self.eirp_dbm - path_loss_db - self.rx_cable_loss_db - polarization_loss_db)


def paper_numbers() -> dict:
    """The figures quoted in the manuscript, recomputed."""
    lb = LinkBudget()
    d_flight = 9.5 * 1609.344
    fs = fspl_db(d_flight, lb.freq_hz)
    epl_test = equivalent_path_loss(113.69, lb.freq_hz, 40.0)
    return {
        "fspl_flight_db": round(fs, 1),
        "eirp_dbm": round(lb.eirp_dbm, 1),
        "rx_power_flight_dbm": round(lb.received_power_dbm(fs), 1),
        "threshold_dbm": round(lb.threshold_dbm, 1),
        "margin_flight_db": round(lb.margin_db(fs), 1),
        "rx_gain_for_30dB_margin_dbi": round(lb.rx_gain_for_margin(fs, 30.0), 1),
        "epl_test_db": round(epl_test, 1),
        "epl_equivalent_range_km": round(distance_for_fspl(epl_test, lb.freq_hz) / 1000, 2),
        "rx_power_test_dbm": round(lb.received_power_dbm(epl_test), 1),
    }
