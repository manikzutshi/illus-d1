from pydantic import BaseModel, Field
from typing import Optional, List

# Standard E24 resistor values (multiplied across decades)
E24_VALUES = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
              3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]

class ResistorCalculation(BaseModel):
    """Result of an LED series resistor calculation."""
    supply_voltage: float = Field(..., description="Supply voltage in volts")
    led_forward_voltage: float = Field(..., description="LED forward voltage in volts")
    target_current_ma: float = Field(..., description="Target LED current in milliamps")
    calculated_resistance: float = Field(..., description="Exact calculated resistance in ohms")
    nearest_standard_value: Optional[float] = Field(None, description="Nearest E24 standard resistor value in ohms")
    actual_current_ma: Optional[float] = Field(None, description="Actual current with nearest standard value in mA")
    power_dissipation_mw: float = Field(..., description="Power dissipated by the resistor in milliwatts")
    assumptions: List[str] = Field(default_factory=list, description="Engineering assumptions made")

def calculate_led_resistor(
    supply_voltage: float,
    led_forward_voltage: float, 
    target_current_ma: float
) -> ResistorCalculation:
    """Calculate the series resistor value for an LED circuit.
    
    Uses Ohm's Law: R = (V_supply - V_forward) / I_target
    
    Args:
        supply_voltage: Supply voltage in volts (e.g. 3.3 or 5.0)
        led_forward_voltage: LED forward voltage drop in volts (e.g. 2.0)
        target_current_ma: Target LED current in milliamps (e.g. 10.0)
    
    Returns:
        ResistorCalculation with all derived values.
    
    Raises:
        ValueError: If inputs are physically invalid.
    """
    # Validate inputs
    if supply_voltage <= 0:
        raise ValueError(f"Supply voltage must be positive, got {supply_voltage}V")
    if led_forward_voltage < 0:
        raise ValueError(f"LED forward voltage must be non-negative, got {led_forward_voltage}V")
    if target_current_ma <= 0:
        raise ValueError(f"Target current must be positive, got {target_current_ma}mA")
    if led_forward_voltage >= supply_voltage:
        raise ValueError(
            f"LED forward voltage ({led_forward_voltage}V) must be less than "
            f"supply voltage ({supply_voltage}V)"
        )
    
    # Calculate
    voltage_drop = supply_voltage - led_forward_voltage
    target_current_a = target_current_ma / 1000.0
    calculated_resistance = voltage_drop / target_current_a
    
    # Find nearest standard E24 value
    nearest = _find_nearest_e24(calculated_resistance)
    
    # Calculate actual current with nearest standard value
    actual_current_ma = None
    if nearest is not None:
        actual_current_a = voltage_drop / nearest
        actual_current_ma = actual_current_a * 1000.0
    
    # Power dissipation: P = I^2 * R (using the calculated resistance)
    power_mw = (target_current_a ** 2) * calculated_resistance * 1000.0
    
    assumptions = [
        "Assumes ideal voltage source (no internal resistance)",
        "Assumes LED forward voltage is constant at specified value",
        "Does not account for temperature effects",
    ]
    
    return ResistorCalculation(
        supply_voltage=supply_voltage,
        led_forward_voltage=led_forward_voltage,
        target_current_ma=target_current_ma,
        calculated_resistance=round(calculated_resistance, 2),
        nearest_standard_value=nearest,
        actual_current_ma=round(actual_current_ma, 2) if actual_current_ma else None,
        power_dissipation_mw=round(power_mw, 2),
        assumptions=assumptions,
    )

def _find_nearest_e24(target: float) -> Optional[float]:
    """Find the nearest E24 standard resistor value."""
    if target <= 0:
        return None
    
    # Generate all standard values from 1 ohm to 10M ohm
    all_values = []
    for decade in range(0, 7):  # 1 to 10M
        multiplier = 10 ** decade
        for base in E24_VALUES:
            all_values.append(round(base * multiplier, 1))
    
    # Find nearest (prefer next value UP for safety - less current is safer)
    # But return the absolute nearest
    best = None
    best_diff = float('inf')
    for val in all_values:
        diff = abs(val - target)
        if diff < best_diff:
            best_diff = diff
            best = val
    
    return best


# ── General engineering calculators (deterministic; used by AI tools and explanations) ──

class CalculationResult(BaseModel):
    """Result of a deterministic engineering calculation."""
    calculation: str
    formula: str
    inputs: dict = Field(default_factory=dict)
    outputs: dict = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)


def _positive(name: str, value: float) -> float:
    if value is None or value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return float(value)


def calculate_voltage_divider(v_in: float, r_top: float, r_bottom: float) -> CalculationResult:
    """Unloaded divider output: Vout = Vin * Rb / (Rt + Rb)."""
    _positive("r_top", r_top); _positive("r_bottom", r_bottom)
    v_out = v_in * r_bottom / (r_top + r_bottom)
    i = v_in / (r_top + r_bottom)
    return CalculationResult(
        calculation="voltage_divider", formula="Vout = Vin·Rb/(Rt+Rb)",
        inputs={"v_in": v_in, "r_top": r_top, "r_bottom": r_bottom},
        outputs={"v_out": round(v_out, 4), "divider_current_ma": round(i * 1000, 4)},
        assumptions=["Load current on the output is negligible compared with the divider current"])


def calculate_rc(r: float, c: float) -> CalculationResult:
    """RC time constant and first-order cutoff frequency."""
    import math
    _positive("r", r); _positive("c", c)
    tau = r * c
    return CalculationResult(
        calculation="rc_time_constant", formula="τ = R·C,  fc = 1/(2πRC)",
        inputs={"r": r, "c": c},
        outputs={"tau_s": float(f"{tau:.6g}"), "cutoff_hz": float(f"{1 / (2 * math.pi * tau):.6g}"),
                 "settle_5tau_s": float(f"{5 * tau:.6g}")},
        assumptions=["Ideal first-order RC network"])


def calculate_bjt_base_resistor(v_drive: float, load_current_ma: float, hfe_min: float,
                                vbe: float = 0.7, overdrive: float = 3.0) -> CalculationResult:
    """Base resistor for a saturated BJT switch: Rb = (Vdrive − Vbe) / (overdrive · Ic / hFEmin)."""
    _positive("load_current_ma", load_current_ma); _positive("hfe_min", hfe_min)
    if v_drive <= vbe:
        raise ValueError(f"Drive voltage {v_drive} V must exceed Vbe {vbe} V")
    ib = overdrive * (load_current_ma / 1000) / hfe_min
    rb = (v_drive - vbe) / ib
    std = _find_nearest_e24(rb)
    # prefer the next *lower* standard value so saturation is kept
    if std and std > rb:
        lower = [v for v in (b * 10 ** d for d in range(0, 7) for b in E24_VALUES) if v <= rb]
        std = round(max(lower), 1) if lower else std
    return CalculationResult(
        calculation="bjt_base_resistor", formula="Rb = (Vdrive − Vbe) / (k·Ic/hFE_min)",
        inputs={"v_drive": v_drive, "load_current_ma": load_current_ma, "hfe_min": hfe_min, "vbe": vbe, "overdrive": overdrive},
        outputs={"base_current_ma": round(ib * 1000, 4), "rb_ohms": round(rb, 1), "rb_standard_ohms": std},
        assumptions=[f"Overdrive factor {overdrive}x ensures saturation", "Vbe(sat) ≈ 0.7 V"])


def calculate_555_astable(r1: float, r2: float, c: float) -> CalculationResult:
    """NE555 astable: f = 1.44 / ((R1 + 2R2)·C), duty = (R1+R2)/(R1+2R2)."""
    _positive("r1", r1); _positive("r2", r2); _positive("c", c)
    f = 1.44 / ((r1 + 2 * r2) * c)
    duty = (r1 + r2) / (r1 + 2 * r2)
    return CalculationResult(
        calculation="astable_555", formula="f = 1.44/((R1+2R2)C),  D = (R1+R2)/(R1+2R2)",
        inputs={"r1": r1, "r2": r2, "c": c},
        outputs={"frequency_hz": float(f"{f:.5g}"), "period_s": float(f"{1 / f:.5g}"), "duty_cycle": round(duty, 4)},
        assumptions=["Bipolar NE555, supply-independent to first order"])


def calculate_noninverting_gain(rf: float, rg: float) -> CalculationResult:
    _positive("rf", rf); _positive("rg", rg)
    return CalculationResult(
        calculation="noninverting_gain", formula="G = 1 + Rf/Rg",
        inputs={"rf": rf, "rg": rg}, outputs={"gain": round(1 + rf / rg, 6)},
        assumptions=["Ideal op-amp within its bandwidth and output swing"])


CALCULATORS = {
    "led_resistor": lambda p: calculate_led_resistor(p["supply_voltage"], p["forward_voltage"], p["target_current_ma"]),
    "voltage_divider": lambda p: calculate_voltage_divider(p["v_in"], p["r_top"], p["r_bottom"]),
    "rc_time_constant": lambda p: calculate_rc(p["r"], p["c"]),
    "bjt_base_resistor": lambda p: calculate_bjt_base_resistor(p["v_drive"], p["load_current_ma"], p["hfe_min"],
                                                               p.get("vbe", 0.7), p.get("overdrive", 3.0)),
    "astable_555": lambda p: calculate_555_astable(p["r1"], p["r2"], p["c"]),
    "noninverting_gain": lambda p: calculate_noninverting_gain(p["rf"], p["rg"]),
}


def run_calculation(calculation: str, params: dict):
    """Dispatch a named calculation. Raises ValueError for unknown names / bad inputs."""
    if calculation not in CALCULATORS:
        raise ValueError(f"Unknown calculation '{calculation}'. Available: {sorted(CALCULATORS)}")
    from core.units import parse_quantity
    values = {}
    for k, v in params.items():
        q = parse_quantity(v)
        if q is None:
            raise ValueError(f"Parameter {k}={v!r} is not a number (engineering notation such as '4.7k' or '100n' is accepted)")
        values[k] = q
    try:
        return CALCULATORS[calculation](values)
    except KeyError as e:
        raise ValueError(f"Missing parameter {e} for {calculation}")
