"""Regenerate the frontend test fixtures (full StudioStates from the backend).

    python scripts/export_frontend_fixture.py

The vitest suite uses them to check that the browser's transform math reproduces the
backend's geometry exactly (cross-language consistency): schematic pin positions from
pwm_state.json, breadboard holes / physical selection from alarm_physical_state.json."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from studio import StudioService  # noqa: E402

svc = StudioService()
fixtures = ROOT / "frontend" / "src" / "studio" / "__fixtures__"
for name, state in (("pwm_state.json", svc.open_example("pwm_motor_controller")),
                    ("alarm_physical_state.json", svc.open_example("temperature_alarm", physical=True))):
    out = fixtures / name
    out.write_text(state.model_dump_json(), encoding="utf-8")
    print(f"wrote {out}")
