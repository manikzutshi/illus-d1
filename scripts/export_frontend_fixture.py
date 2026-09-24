"""Regenerate the frontend test fixture (a full StudioState from the backend).

    python scripts/export_frontend_fixture.py

The vitest suite uses it to check that the browser's transform math reproduces the
backend's pin geometry exactly (cross-language consistency)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from studio import StudioService  # noqa: E402

state = StudioService().open_example("pwm_motor_controller")
out = ROOT / "frontend" / "src" / "studio" / "__fixtures__" / "pwm_state.json"
out.write_text(state.model_dump_json(), encoding="utf-8")
print(f"wrote {out}")
