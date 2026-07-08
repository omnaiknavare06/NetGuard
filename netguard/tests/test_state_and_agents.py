from agents.base import BaseAgent
from state_manager import StateManager


def test_reset_restores_capacity_thresholds() -> None:
    state = StateManager()
    state.execute_action("enable_queue_mode", "Enable queue mode")
    state.execute_action("enable_queue_mode", "Enable queue mode again")
    assert state.MAX_NORMAL < 10

    state.reset()

    assert state.MAX_NORMAL == 10
    assert state.MAX_REJECT == 15


def test_base_agent_parse_json_handles_non_json_text() -> None:
    raw = "prefix text ```json\n{\"severity\": \"High\"}\n``` suffix"
    parsed = BaseAgent._parse_json(raw)
    assert parsed["severity"] == "High"

    fallback = BaseAgent._parse_json("no valid json here")
    assert fallback == {}


def test_block_ip_ignores_localhost_and_private_ips() -> None:
    state = StateManager()
    action = state.execute_action("block_ip", "Block suspicious ip", detail="127.0.0.1,192.168.1.10")
    assert "Blocked 0 IP" in action["result"]
    assert len(state.blacklisted_ips) == 0
