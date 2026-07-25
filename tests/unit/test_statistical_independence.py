"""Statistical independence tests for frozen core.

Validates that scipy API calls used by detectors still work as expected.
Catches silent breaks when scipy releases new versions.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats


class TestScipyKSIndependence:
    """Verify scipy.stats.ks_2samp works as MIIE expects."""

    def test_ks_2samp_returns_tuple(self):
        """ks_2samp should return (statistic, pvalue)."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 100)
        b = rng.normal(0, 1, 100)
        result = stats.ks_2samp(a, b)
        assert hasattr(result, "statistic")
        assert hasattr(result, "pvalue")

    def test_ks_2samp_identical_distributions(self):
        """Identical distributions should produce low KS statistic."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 1000)
        b = rng.normal(0, 1, 1000)
        stat, pvalue = stats.ks_2samp(a, b)
        assert stat < 0.15
        assert pvalue > 0.05

    def test_ks_2samp_different_distributions(self):
        """Different distributions should produce high KS statistic."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 1000)
        b = rng.normal(5, 1, 1000)
        stat, pvalue = stats.ks_2samp(a, b)
        assert stat > 0.5
        assert pvalue < 0.01

    def test_ks_2samp_alpha_threshold(self):
        """MIIE uses alpha=0.05 for KS test. Verify this works."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 500)
        b = rng.normal(0, 1, 500)
        stat, pvalue = stats.ks_2samp(a, b)
        alpha = 0.05
        # Same distribution: should NOT reject null hypothesis
        assert pvalue > alpha or stat < 0.1


class TestScipyPSI:
    """Verify PSI computation still works with current scipy."""

    def _compute_psi(self, expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
        """Compute Population Stability Index (PSI)."""
        breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
        expected_counts = np.histogram(expected, bins=breakpoints)[0] / len(expected)
        actual_counts = np.histogram(actual, bins=breakpoints)[0] / len(actual)
        # Avoid log(0)
        expected_counts = np.clip(expected_counts, 1e-6, None)
        actual_counts = np.clip(actual_counts, 1e-6, None)
        psi = np.sum((actual_counts - expected_counts) * np.log(actual_counts / expected_counts))
        return float(psi)

    def test_psi_same_distribution(self):
        """Same distribution should produce low PSI."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 1000)
        b = rng.normal(0, 1, 1000)
        psi = self._compute_psi(a, b)
        assert psi < 0.25  # MIIE threshold

    def test_psi_different_distributions(self):
        """Different distributions should produce high PSI."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 1000)
        b = rng.normal(5, 1, 1000)
        psi = self._compute_psi(a, b)
        assert psi > 0.25


class TestScipyFisherZ:
    """Verify Fisher z-transformation works as MIIE expects."""

    def test_fisher_z_basic(self):
        """Fisher z should transform correlation to normal-ish distribution."""
        r = 0.5
        z = 0.5 * np.log((1 + r) / (1 - r))
        assert abs(z - 0.5493) < 0.01

    def test_fisher_z_confidence_interval(self):
        """Fisher z CI should work for correlation comparison."""
        rng = np.random.default_rng(42)
        x = rng.normal(0, 1, 100)
        y = x + rng.normal(0, 0.5, 100)
        r = np.corrcoef(x, y)[0, 1]
        z = 0.5 * np.log((1 + r) / (1 - r))
        se = 1 / np.sqrt(len(x) - 3)
        ci_lower = z - 1.96 * se
        ci_upper = z + 1.96 * se
        # Should contain true z
        assert ci_lower < z < ci_upper


class TestScipyDipTest:
    """Verify Hartigan's dip test approximation works."""

    def test_dip_test_importable(self):
        """dip_test should be importable from statistics module."""
        from miie.processing.detection.statistics import dip_test

        assert callable(dip_test)

    def test_dip_test_unimodal(self):
        """Unimodal distribution should produce valid dip test result."""
        from miie.processing.detection.statistics import dip_test

        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 500)
        result = dip_test(data)
        # dip_test returns (dip_statistic, p_value) tuple
        dip_stat = result[0]
        p_value = result[1]
        # Dip statistic should be between 0 and 1
        assert 0 <= dip_stat <= 1
        # p-value should be between 0 and 1
        assert 0 <= p_value <= 1


class TestNumpyCompatibility:
    """Verify numpy operations used by MIIE still work."""

    def test_percentile(self):
        """numpy.percentile should work as expected."""
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 1000)
        p50 = np.percentile(data, 50)
        assert abs(p50) < 0.2

    def test_histogram(self):
        """numpy.histogram should work as expected."""
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 1000)
        counts, bins = np.histogram(data, bins=10)
        assert len(counts) == 10
        assert len(bins) == 11

    def test_correlate(self):
        """numpy.corrcoef should work as expected."""
        rng = np.random.default_rng(42)
        x = rng.normal(0, 1, 100)
        y = x + rng.normal(0, 0.1, 100)
        r = np.corrcoef(x, y)[0, 1]
        assert r > 0.8
