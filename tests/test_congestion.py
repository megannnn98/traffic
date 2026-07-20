import pytest

from almaty_traffic.congestion import classify_congestion, compute_congestion
from almaty_traffic.models import CongestionLevel


class TestClassifyCongestion:
    def test_free(self) -> None:
        assert classify_congestion(1.19) == CongestionLevel.FREE

    def test_free_boundary(self) -> None:
        assert classify_congestion(1.1999) == CongestionLevel.FREE

    def test_light_lower(self) -> None:
        assert classify_congestion(1.20) == CongestionLevel.LIGHT

    def test_light(self) -> None:
        assert classify_congestion(1.35) == CongestionLevel.LIGHT

    def test_light_upper(self) -> None:
        assert classify_congestion(1.49) == CongestionLevel.LIGHT

    def test_dense_lower(self) -> None:
        assert classify_congestion(1.50) == CongestionLevel.DENSE

    def test_dense(self) -> None:
        assert classify_congestion(1.75) == CongestionLevel.DENSE

    def test_dense_upper(self) -> None:
        assert classify_congestion(1.99) == CongestionLevel.DENSE

    def test_traffic_jam_lower(self) -> None:
        assert classify_congestion(2.0) == CongestionLevel.TRAFFIC_JAM

    def test_traffic_jam(self) -> None:
        assert classify_congestion(2.5) == CongestionLevel.TRAFFIC_JAM

    def test_traffic_jam_upper(self) -> None:
        assert classify_congestion(2.99) == CongestionLevel.TRAFFIC_JAM

    def test_severe_traffic_jam(self) -> None:
        assert classify_congestion(3.0) == CongestionLevel.SEVERE_TRAFFIC_JAM

    def test_severe_traffic_jam_high(self) -> None:
        assert classify_congestion(5.0) == CongestionLevel.SEVERE_TRAFFIC_JAM


class TestComputeCongestion:
    def test_normal(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            duration_seconds=600,
            free_flow_duration_seconds=240,
        )
        assert result.segment_id == "seg1"
        assert result.duration_seconds == 600
        assert result.free_flow_duration_seconds == 240
        assert result.delay_seconds == 360
        assert result.congestion_ratio == pytest.approx(2.5)
        assert result.congestion_level == CongestionLevel.TRAFFIC_JAM

    def test_no_free_flow(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            duration_seconds=600,
            free_flow_duration_seconds=0,
        )
        assert result.congestion_level == CongestionLevel.UNKNOWN
        assert result.congestion_ratio is None
        assert result.delay_seconds == 0

    def test_negative_delay_clamped(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            duration_seconds=100,
            free_flow_duration_seconds=240,
        )
        assert result.delay_seconds == 0
        assert result.congestion_ratio == pytest.approx(100 / 240)

    def test_none_duration(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            duration_seconds=None,
            free_flow_duration_seconds=240,
        )
        assert result.congestion_level == CongestionLevel.UNKNOWN
        assert result.congestion_ratio is None
        assert result.delay_seconds == 0
