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
