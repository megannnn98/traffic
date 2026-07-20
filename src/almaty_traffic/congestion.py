from almaty_traffic.models import CongestionLevel, CongestionResult

# Пороги классификации загруженности (congestion_ratio)
FREE_THRESHOLD = 1.20
LIGHT_THRESHOLD = 1.50
DENSE_THRESHOLD = 2.00
TRAFFIC_JAM_THRESHOLD = 3.00


def classify_congestion(ratio: float) -> CongestionLevel:
    """Классифицировать загруженность по отношению текущего времени к базовому."""
    if ratio < FREE_THRESHOLD:
        return CongestionLevel.FREE
    if ratio < LIGHT_THRESHOLD:
        return CongestionLevel.LIGHT
    if ratio < DENSE_THRESHOLD:
        return CongestionLevel.DENSE
    if ratio < TRAFFIC_JAM_THRESHOLD:
        return CongestionLevel.TRAFFIC_JAM
    return CongestionLevel.SEVERE_TRAFFIC_JAM


def compute_congestion(
    segment_id: str,
    current_travel_time: int | None,
    free_flow_travel_time: int,
    current_speed: int | None = None,
    free_flow_speed: int | None = None,
    confidence: float | None = None,
    road_closure: bool = False,
) -> CongestionResult:
    """Вычислить загруженность участка по данным TomTom."""
    if road_closure:
        return CongestionResult(
            segment_id=segment_id,
            current_speed_kmh=current_speed,
            free_flow_speed_kmh=free_flow_speed,
            current_travel_time_seconds=current_travel_time,
            free_flow_travel_time_seconds=free_flow_travel_time,
            confidence=confidence,
            road_closure=True,
            congestion_ratio=None,
            congestion_level=CongestionLevel.SEVERE_TRAFFIC_JAM,
        )

    if free_flow_travel_time <= 0 or current_travel_time is None:
        return CongestionResult(
            segment_id=segment_id,
            current_speed_kmh=current_speed,
            free_flow_speed_kmh=free_flow_speed,
            current_travel_time_seconds=current_travel_time,
            free_flow_travel_time_seconds=free_flow_travel_time,
            confidence=confidence,
            road_closure=road_closure,
            congestion_ratio=None,
            congestion_level=CongestionLevel.UNKNOWN,
        )

    ratio = current_travel_time / free_flow_travel_time

    return CongestionResult(
        segment_id=segment_id,
        current_speed_kmh=current_speed,
        free_flow_speed_kmh=free_flow_speed,
        current_travel_time_seconds=current_travel_time,
        free_flow_travel_time_seconds=free_flow_travel_time,
        confidence=confidence,
        road_closure=road_closure,
        congestion_ratio=ratio,
        congestion_level=classify_congestion(ratio),
    )
