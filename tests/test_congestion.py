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
            current_travel_time=153,
            free_flow_travel_time=90,
            current_speed=41,
            free_flow_speed=70,
            confidence=0.59,
        )
        assert result.segment_id == "seg1"
        assert result.current_speed_kmh == 41
        assert result.free_flow_speed_kmh == 70
        assert result.current_travel_time_seconds == 153
        assert result.free_flow_travel_time_seconds == 90
        assert result.confidence == 0.59
        assert result.congestion_ratio == pytest.approx(153 / 90)
        assert result.congestion_level == CongestionLevel.DENSE

    def test_no_free_flow(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            current_travel_time=153,
            free_flow_travel_time=0,
        )
        assert result.congestion_level == CongestionLevel.UNKNOWN
        assert result.congestion_ratio is None

    def test_none_duration(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            current_travel_time=None,
            free_flow_travel_time=90,
        )
        assert result.congestion_level == CongestionLevel.UNKNOWN
        assert result.congestion_ratio is None

    def test_road_closure(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            current_travel_time=0,
            free_flow_travel_time=90,
            road_closure=True,
        )
        assert result.road_closure is True
        assert result.congestion_level == CongestionLevel.SEVERE_TRAFFIC_JAM
        assert result.congestion_ratio is None

    def test_speed_ratio(self) -> None:
        result = compute_congestion(
            segment_id="seg1",
            current_travel_time=153,
            free_flow_travel_time=90,
            current_speed=41,
            free_flow_speed=70,
        )
        assert result.current_speed_kmh == 41
        assert result.free_flow_speed_kmh == 70
