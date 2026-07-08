from pathlib import Path

import logger


def test_incident_stats_and_clear_with_temp_dirs(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    incident_dir = tmp_path / "incidents"
    log_file = log_dir / "system.log"

    monkeypatch.setattr(logger, "LOG_DIR", log_dir)
    monkeypatch.setattr(logger, "INCIDENT_DIR", incident_dir)
    monkeypatch.setattr(logger, "LOG_FILE", log_file)

    logger.ensure_storage()
    assert logger.incident_stats()["total"] == 0

    logger.save_incident({"a": 1})
    logger.save_incident({"b": 2})

    stats = logger.incident_stats()
    assert stats["total"] == 2
    assert stats["latest"] is not None

    removed = logger.clear_incidents()
    assert removed == 2
    assert logger.incident_stats()["total"] == 0
