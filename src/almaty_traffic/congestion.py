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
    duration_seconds: int | None,
    free_flow_duration_seconds: int,
) -> CongestionResult:
    """Вычислить загруженность участка."""
    if free_flow_duration_seconds <= 0 or duration_seconds is None:
        return CongestionResult(
            segment_id=segment_id,
            duration_seconds=duration_seconds,
            free_flow_duration_seconds=free_flow_duration_seconds,
            delay_seconds=0,
            congestion_ratio=None,
            congestion_level=CongestionLevel.UNKNOWN,
        )

    ratio = duration_seconds / free_flow_duration_seconds
    delay = max(0, duration_seconds - free_flow_duration_seconds)

    return CongestionResult(
        segment_id=segment_id,
        duration_seconds=duration_seconds,
        free_flow_duration_seconds=free_flow_duration_seconds,
        delay_seconds=delay,
        congestion_ratio=ratio,
        congestion_level=classify_congestion(ratio),
    )
