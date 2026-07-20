import httpx
import pytest

from almaty_traffic.models import MeasurementStatus, TrafficMeasurement, TrafficSegment
from almaty_traffic.tomtom_client import TomTomTrafficClient


def _segment(seg_id: str = "seg1") -> TrafficSegment:
    return TrafficSegment(
        id=seg_id,
        road="проспект",
        direction="восток",
        from_name="А",
        to_name="Б",
        origin={"latitude": 43.2381, "longitude": 76.9452},
        destination={"latitude": 43.2384, "longitude": 76.9281},
        free_flow_duration_seconds=240,
        enabled=True,
    )


def _ok_response(
    current_speed: int = 41,
    free_flow_speed: int = 70,
    current_travel_time: int = 153,
    free_flow_travel_time: int = 90,
    confidence: float = 0.59,
    road_closure: bool = False,
) -> httpx.Response:
    body = {
        "flowSegmentData": {
            "frc": "FRC2",
            "currentSpeed": current_speed,
            "freeFlowSpeed": free_flow_speed,
            "currentTravelTime": current_travel_time,
            "freeFlowTravelTime": free_flow_travel_time,
            "confidence": confidence,
            "roadClosure": road_closure,
            "coordinates": {
                "coordinate": [
                    {"latitude": 43.2381, "longitude": 76.9452},
                ]
            },
        }
    }
    return httpx.Response(200, json=body)


def _error_response(status_code: int, message: str = "error") -> httpx.Response:
    return httpx.Response(
        status_code,
        json={
            "error": message,
            "httpStatusCode": status_code,
            "detailedError": {"code": "ERROR", "message": message},
        },
    )


def _broken_json_response() -> httpx.Response:
    return httpx.Response(200, text="not json at all")


async def _get_measurements(
    handler, segments: list[TrafficSegment] | None = None
) -> list[TrafficMeasurement]:
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = TomTomTrafficClient(
            http_client=http,
            api_key="test_key",
            timeout_seconds=10,
        )
        segs = segments or [_segment()]
        return await client.get_segments(segs)


class TestGetSegments:
    @pytest.mark.asyncio
    async def test_successful_response(self) -> None:
        results = await _get_measurements(lambda req: _ok_response())
        assert len(results) == 1
        m = results[0]
        assert m.status == MeasurementStatus.OK
        assert m.current_speed_kmh == 41
        assert m.free_flow_speed_kmh == 70
        assert m.current_travel_time_seconds == 153
        assert m.free_flow_travel_time_seconds == 90
        assert m.confidence == 0.59
        assert m.road_closure is False
        assert m.segment_id == "seg1"

    @pytest.mark.asyncio
    async def test_403_forbidden(self) -> None:
        results = await _get_measurements(lambda req: _error_response(403, "Forbidden"))
        m = results[0]
        assert m.status == MeasurementStatus.FAIL
        assert m.error_message is not None
        assert "403" in m.error_message

    @pytest.mark.asyncio
    async def test_429_rate_limit(self) -> None:
        results = await _get_measurements(lambda req: _error_response(429, "Too Many Requests"))
        m = results[0]
        assert m.status == MeasurementStatus.FAIL
        assert m.error_message is not None

    @pytest.mark.asyncio
    async def test_500_server_error(self) -> None:
        results = await _get_measurements(lambda req: _error_response(500, "Internal Server Error"))
        m = results[0]
        assert m.status == MeasurementStatus.FAIL

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout")

        results = await _get_measurements(handler)
        m = results[0]
        assert m.status == MeasurementStatus.FAIL
        assert m.error_message is not None

    @pytest.mark.asyncio
    async def test_broken_json(self) -> None:
        results = await _get_measurements(lambda req: _broken_json_response())
        m = results[0]
        assert m.status == MeasurementStatus.FAIL
        assert m.error_message is not None

    @pytest.mark.asyncio
    async def test_road_closure(self) -> None:
        results = await _get_measurements(
            lambda req: _ok_response(road_closure=True, current_speed=0)
        )
        m = results[0]
        assert m.status == MeasurementStatus.OK
        assert m.road_closure is True
        assert m.current_speed_kmh == 0

    @pytest.mark.asyncio
    async def test_low_confidence(self) -> None:
        results = await _get_measurements(lambda req: _ok_response(confidence=0.0))
        m = results[0]
        assert m.status == MeasurementStatus.OK
        assert m.confidence == 0.0

    @pytest.mark.asyncio
    async def test_partial_success(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _ok_response()
            return _error_response(500, "Server Error")

        segs = [_segment("ok_seg"), _segment("fail_seg")]
        results = await _get_measurements(handler, segments=segs)
        assert len(results) == 2
        statuses = {r.segment_id: r.status for r in results}
        assert statuses["ok_seg"] == MeasurementStatus.OK
        assert statuses["fail_seg"] == MeasurementStatus.FAIL

    @pytest.mark.asyncio
    async def test_multiple_segments(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _ok_response(current_speed=60, free_flow_speed=80)

        segs = [_segment("a"), _segment("b"), _segment("c")]
        results = await _get_measurements(handler, segments=segs)
        assert len(results) == 3
        assert all(r.status == MeasurementStatus.OK for r in results)
