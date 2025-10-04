# Fatigue calculation logic

def compute_fatigue(hours_online: float, jobs_completed: int) -> float:
    MAX_HOURS_CONTINUOUS = 5
    hour_fatigue = min(1.0, (hours_online / MAX_HOURS_CONTINUOUS))
    job_fatigue = min(1.0, (jobs_completed / 50))
    return min(1.0, (hour_fatigue * 0.7) + (job_fatigue * 0.3))
