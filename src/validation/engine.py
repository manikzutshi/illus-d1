"""Deterministic validation engine for Engineering Design Project instances.

Error codes:
    E001  UNKNOWN_COMPONENT_TYPE       Component type not in registry
    E002  UNKNOWN_PIN                  Pin not defined on component type
    E003  DUPLICATE_INSTANCE_ID        Two instances share the same ID
    E004  MISSING_POWER                No POWER pin connected in any net
    E005  MISSING_GROUND               No GROUND pin connected in any net
    E006  INVALID_CONNECTION_ENDPOINT  PinRef references a non-existent instance
    E007  LED_REQUIRES_RESISTOR        LED has no resistor on any connected net
    E008  DUPLICATE_NET_ID             Two nets share the same ID
    E009  DISCONNECTED_COMPONENT       Component has no pins in any net
    E010  VOLTAGE_INCOMPATIBLE         Output voltage exceeds input max_voltage on same net
    E011  SHORT_CIRCUIT                POWER and GROUND pins directly connected on same net
    E012  LOGIC_INVALID_INSTANCE       Logic rule references a non-existent component instance
    E013  PIN_ON_MULTIPLE_NETS         One pin appears in more than one net
    E014  OPERATING_VOLTAGE            Supplied rail voltage outside a part's operating range
    E015  GPIO_OVERCURRENT             Loads on a GPIO net exceed the pin's drive limit
    E016  MISSING_POWER_SOURCE         Net has POWER pins but nothing that supplies it
    E017  FLYBACK_DIODE_MISSING        Inductive load (constraint severity ERROR) has no clamp diode
    E018  POLARITY_REVERSED            Polarised part wired backwards across a supply
    E019  SOURCE_RETURN_OPEN           A supply source drives a net but its ground terminal is unconnected

Warning codes:
    W001  MISSING_RESISTOR_VALUE       Resistor instance has no 'resistance' parameter
    W002  VOLTAGE_NOT_CHECKABLE        Voltage metadata missing; cannot verify compatibility
    W003  SERIES_RESISTOR_RECOMMENDED  Part asks for a series/base resistor that is not present
    W004  PULLUP_MISSING               Open-drain / 1-Wire / I2C pin has no pull-up to a supply
    W005  FLYBACK_DIODE_RECOMMENDED    Inductive load (constraint severity WARNING) has no clamp diode
    W006  DECOUPLING_MISSING           Required supply decoupling capacitor absent (INFO level goes to infos)
    W007  SUPPLY_UNCONNECTED           A part's supply-input pins are all unconnected

Constraint-driven rules (E007 generalisation, E017, W003-W006) read `design_constraints`
from the registry, so new parts gain checks through data rather than code.

All rules are deterministic. No LLM dependency.
"""
from core.models import (
    ComponentType,
    EngineeringDesignProject,
    ValidationCheck,
    ValidationResult,
    ValidationError,
    PinDefinition
)
from core.units import parse_quantity
from core.enums import ValidationStatus, ValidationSeverity, PinDirection, ComponentCategory, ObjectType
from components.registry import ComponentRegistry


class DesignValidator:
    """Deterministic validator for Engineering Design Project instances.
    Does NOT use any LLM. All rules are explicit."""

    def __init__(self, registry: ComponentRegistry):
        self._registry = registry

    CHECKS = [
        ("E001", "Unknown component type", "_check_unknown_components"),
        ("E003", "Duplicate instance id", "_check_duplicate_instances"),
        ("E002", "Unknown pin", "_check_unknown_pins"),
        ("E004", "Power present", "_check_dangling_power"),
        ("E005", "Ground present", "_check_dangling_ground"),
        ("E006", "Connection endpoints exist", "_check_invalid_connections"),
        ("E007", "LED current limiting", "_check_led_resistor"),
        ("E008", "Duplicate net id", "_check_duplicate_nets"),
        ("E009", "Every component connected", "_check_disconnected_components"),
        ("E013", "Pin on one net only", "_check_multiple_nets_per_pin"),
        ("E014", "Operating voltage", "_check_operating_voltage"),
        ("E015", "GPIO drive current", "_check_gpio_drive_limit"),
        ("E016", "Power nets have a source", "_check_missing_power_source"),
        ("E010", "Logic-level compatibility", "_check_voltage_compatibility"),
        ("E011", "Supply short circuit", "_check_short_circuit"),
        ("E012", "Logic rules reference real parts", "_check_logic_instances"),
        ("E017/W005", "Flyback diodes on inductive loads", "_check_flyback"),
        ("E018", "Polarity of polarised parts", "_check_polarity"),
        ("E019", "Supply sources have a return path", "_check_source_return"),
        ("W007", "Parts receive supply", "_check_supply_inputs"),
        ("W001", "Resistor values specified", "_check_resistor_parameters"),
        ("W002", "Voltage metadata coverage", "_check_voltage_metadata_coverage"),
        ("W003", "Recommended series resistors", "_check_series_constraints"),
        ("W004", "Pull-up resistors", "_check_pullups"),
        ("W006", "Decoupling capacitors", "_check_decoupling"),
    ]

    def validate(self, design: EngineeringDesignProject) -> ValidationResult:
        """Run all validation checks and return a deterministic result."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        infos: list[ValidationError] = []
        checks: list[ValidationCheck] = []

        # Build lookup dictionaries for efficiency
        self._instance_map = {comp.instance_id: comp for comp in design.components}
        self._not_applicable: set[str] = set()

        for code, name, method in self.CHECKS:
            found = getattr(self, method)(design)
            outcome = "PASS"
            for item in found:
                if item.severity == ValidationSeverity.ERROR:
                    errors.append(item)
                    outcome = "FAIL"
                elif item.severity == ValidationSeverity.WARNING:
                    warnings.append(item)
                    if outcome != "FAIL":
                        outcome = "WARN"
                else:
                    infos.append(item)
            if method in self._not_applicable and not found:
                outcome = "NOT_APPLICABLE"
            checks.append(ValidationCheck(code=code, name=name, outcome=outcome))

        status = ValidationStatus.FAIL if errors else ValidationStatus.PASS
        return ValidationResult(
            status=status,
            errors=errors,
            warnings=warnings,
            infos=infos,
            component_count=len(design.components),
            net_count=len(design.nets),
            checks_run=checks,
        )

    # ── Helpers ──

    def _resolve_pin_def(self, instance_id: str, pin_id: str) -> PinDefinition | None:
        """Resolve a (instance_id, pin_id) pair to a PinDefinition from the registry.
        Returns None if the instance, component type, or pin cannot be resolved."""
        comp = self._instance_map.get(instance_id)
        if not comp:
            return None
        ctype = self._registry.get(comp.component_type)
        if not ctype:
            return None
        return next((p for p in ctype.pins if p.pin_id == pin_id), None)

    def _ctype_of(self, instance_id: str) -> ComponentType | None:
        comp = self._instance_map.get(instance_id)
        return self._registry.get(comp.component_type) if comp else None

    def _source_voltage(self, instance_id: str, pin_id: str) -> tuple[bool, float | None]:
        """(is_supply_source, voltage) for a pin.

        A pin supplies a rail if the registry says so (``supply: source``), or - for legacy
        entries without that field - if it is a POWER pin of a POWER_SOURCE component.
        Voltage comes from, in order: the pin's nominal_voltage, the instance's configurable
        'voltage' parameter, the pin's electrical_type, the component's 'voltage' property.
        Unknown stays None."""
        comp = self._instance_map.get(instance_id)
        ctype = self._ctype_of(instance_id)
        pin = self._resolve_pin_def(instance_id, pin_id)
        if comp is None or ctype is None or pin is None or pin.direction != PinDirection.POWER:
            return False, None
        if pin.supply == "sink":
            return False, None
        if not (pin.supply == "source" or ctype.category == ComponentCategory.POWER_SOURCE):
            return False, None
        v = pin.nominal_voltage
        if v is None and "voltage" in comp.parameters and "voltage" in ctype.configurable_parameters:
            v = parse_quantity(comp.parameters["voltage"], "V")
        if v is None and pin.electrical_type:
            v = self._parse_voltage(pin.electrical_type)
        if v is None:
            v = self._parse_voltage(ctype.electrical_properties.get("voltage", ""))
        return True, v

    def _net_has_source(self, net) -> bool:
        return any(self._source_voltage(pr.instance_id, pr.pin_id)[0] for pr in net.connections)

    def _net_is_ground(self, net) -> bool:
        if (net.net_type or "").lower() == "ground":
            return True
        for pr in net.connections:
            pd = self._resolve_pin_def(pr.instance_id, pr.pin_id)
            if pd is not None and pd.direction == PinDirection.GROUND:
                return True
        return False

    def _net_is_supply(self, net) -> bool:
        """A positive supply rail: driven by a source, or declared power, and not ground."""
        if self._net_is_ground(net):
            return False
        return self._net_has_source(net) or (net.net_type or "").lower() == "power"

    def _net_of(self, design, instance_id: str, pin_id: str):
        for net in design.nets:
            for pr in net.connections:
                if pr.instance_id == instance_id and pr.pin_id == pin_id:
                    return net
        return None

    def _is_resistor(self, instance_id: str) -> bool:
        comp = self._instance_map.get(instance_id)
        ctype = self._ctype_of(instance_id)
        if comp and comp.component_type.startswith("passive:resistor"):
            return True
        return bool(ctype and ctype.family in ("resistor", "potentiometer"))

    def _has_power_semantics(self, design) -> bool:
        """True if any part in the design has supply or ground pins. Pure gate-level or
        idealised diagrams have none and are not required to show a supply."""
        for comp in design.components:
            ctype = self._registry.get(comp.component_type)
            if ctype is None or any(p.direction in (PinDirection.POWER, PinDirection.GROUND) for p in ctype.pins):
                return True
        return False

    # ── E001: Unknown component type ──

    def _check_unknown_components(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        for comp in design.components:
            if not self._registry.has(comp.component_type):
                errors.append(ValidationError(
                    code="E001",
                    message=f"Unknown component type: {comp.component_type}",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=[comp.instance_id],
                    validator='design_validator'
                ))
        return errors

    # ── E002: Unknown pin ──

    def _check_unknown_pins(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        for net in design.nets:
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                if comp and self._registry.has(comp.component_type):
                    ctype = self._registry.get(comp.component_type)
                    pin_ids = {p.pin_id for p in ctype.pins}
                    if pinref.pin_id not in pin_ids:
                        errors.append(ValidationError(
                            code="E002",
                            message=f"Unknown pin {pinref.pin_id} on instance {pinref.instance_id}",
                            severity=ValidationSeverity.ERROR,
                            affected_instances=[pinref.instance_id],
                            affected_pins=[pinref.ref],
                            affected_nets=[net.net_id],
                            validator='design_validator'
                        ))
        return errors

    # ── E003: Duplicate instance ID ──

    def _check_duplicate_instances(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        seen: set[str] = set()
        for comp in design.components:
            if comp.instance_id in seen:
                errors.append(ValidationError(
                    code="E003",
                    message=f"Duplicate instance ID: {comp.instance_id}",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=[comp.instance_id],
                    validator='design_validator'
                ))
            seen.add(comp.instance_id)
        return errors

    # ── E004: Missing power ──

    def _check_dangling_power(self, design: EngineeringDesignProject) -> list[ValidationError]:
        for net in design.nets:
            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def and pin_def.direction == PinDirection.POWER:
                    return []
        if design.components and self._has_power_semantics(design):
            return [ValidationError(
                code="E004",
                message="No connected POWER pins found in any net.",
                severity=ValidationSeverity.ERROR,
                validator='design_validator'
            )]
        return []

    # ── E005: Missing ground ──

    def _check_dangling_ground(self, design: EngineeringDesignProject) -> list[ValidationError]:
        for net in design.nets:
            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def and pin_def.direction == PinDirection.GROUND:
                    return []
        if design.components and self._has_power_semantics(design):
            return [ValidationError(
                code="E005",
                message="No connected GROUND pins found in any net.",
                severity=ValidationSeverity.ERROR,
                validator='design_validator'
            )]
        return []

    # ── E006: Invalid connection endpoint ──

    def _check_invalid_connections(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        for net in design.nets:
            for pinref in net.connections:
                if pinref.instance_id not in self._instance_map:
                    errors.append(ValidationError(
                        code="E006",
                        message=f"PinRef refers to unknown instance ID: {pinref.instance_id}",
                        severity=ValidationSeverity.ERROR,
                        affected_pins=[pinref.ref],
                        affected_nets=[net.net_id],
                        validator='design_validator'
                    ))
        return errors

    # ── E007: LED requires resistor ──

    def _check_led_resistor(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        # Find all nets that have a resistor connected
        resistor_nets: set[str] = set()
        for net in design.nets:
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                if comp and comp.component_type.startswith('passive:resistor'):
                    resistor_nets.add(net.net_id)
                    break

        def needs_resistor(comp) -> bool:
            if comp.component_type.startswith('passive:led'):
                return True
            ctype = self._registry.get(comp.component_type)
            if ctype is None:
                return False
            return ctype.family == "led" or any(c.kind == "series_resistor" and c.severity == "ERROR"
                                                for c in ctype.design_constraints)

        if not any(needs_resistor(c) for c in design.components):
            self._not_applicable.add("_check_led_resistor")
        for comp in design.components:
            if needs_resistor(comp):
                has_resistor = False
                for net in design.nets:
                    for pinref in net.connections:
                        if pinref.instance_id == comp.instance_id and net.net_id in resistor_nets:
                            has_resistor = True
                            break
                    if has_resistor:
                        break

                if not has_resistor:
                    errors.append(ValidationError(
                        code="E007",
                        message=f"LED {comp.instance_id} requires a resistor in series",
                        severity=ValidationSeverity.ERROR,
                        affected_instances=[comp.instance_id],
                        validator='design_validator'
                    ))
        return errors

    # ── E008: Duplicate net ID ──

    def _check_duplicate_nets(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        seen: set[str] = set()
        for net in design.nets:
            if net.net_id in seen:
                errors.append(ValidationError(
                    code="E008",
                    message=f"Duplicate net ID: {net.net_id}",
                    severity=ValidationSeverity.ERROR,
                    affected_nets=[net.net_id],
                    validator='design_validator'
                ))
            seen.add(net.net_id)
        return errors

    # ── E009: Disconnected component ──

    def _check_disconnected_components(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        connected_instances: set[str] = set()
        for net in design.nets:
            for pinref in net.connections:
                connected_instances.add(pinref.instance_id)

        for comp in design.components:
            if comp.instance_id not in connected_instances:
                errors.append(ValidationError(
                    code="E009",
                    message=f"Component {comp.instance_id} is disconnected",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=[comp.instance_id],
                    validator='design_validator'
                ))
        return errors

    # ── E013: Multiple nets per pin ──

    def _check_multiple_nets_per_pin(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        seen_pins: dict[str, str] = {}
        for net in design.nets:
            for pinref in net.connections:
                pref = pinref.ref
                if pref in seen_pins:
                    errors.append(ValidationError(
                        code="E013",
                        message=f"Pin {pref} is connected to multiple nets: {seen_pins[pref]} and {net.net_id}",
                        severity=ValidationSeverity.ERROR,
                        affected_pins=[pref],
                        affected_nets=[seen_pins[pref], net.net_id],
                        validator='design_validator'
                    ))
                else:
                    seen_pins[pref] = net.net_id
        return errors

    # ── E014: Incompatible Operating Voltage ──

    def _parse_voltage(self, v_str: str) -> float | None:
        import re
        if not v_str: return None
        match = re.search(r"([\d\.]+)\s*V", str(v_str))
        if match: return float(match.group(1))
        return None

    def _parse_voltage_range(self, v_str: str) -> tuple[float, float] | None:
        import re
        if not v_str: return None
        match = re.search(r"([\d\.]+)\s*V\s*-\s*([\d\.]+)\s*V", str(v_str))
        if match: return float(match.group(1)), float(match.group(2))
        v = self._parse_voltage(v_str)
        if v is not None: return v, v
        return None

    def _check_operating_voltage(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        net_voltages = {}

        for net in design.nets:
            provided_v = None
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if not comp or not pin_def: continue
                ctype = self._registry.get(comp.component_type)
                if not ctype: continue

                is_src, src_v = self._source_voltage(pinref.instance_id, pinref.pin_id)
                if is_src and src_v is not None:
                    provided_v = src_v
                    break
                # Legacy: MCU power pins without explicit supply metadata.
                if ctype.category == ComponentCategory.MICROCONTROLLER and pin_def.supply is None:
                    if pin_def.direction == PinDirection.POWER:
                        v = self._parse_voltage(pin_def.electrical_type)
                        if v is None and pin_def.max_voltage in (3.3, 5.0):
                            v = pin_def.max_voltage
                        if v is None and ctype.electrical_properties:
                            v = self._parse_voltage(ctype.electrical_properties.get("voltage", ""))
                        if v is not None:
                            provided_v = v
                            break
            if provided_v is not None:
                net_voltages[net.net_id] = provided_v

        for net in design.nets:
            net_v = net_voltages.get(net.net_id)
            if net_v is None: continue
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if not comp or not pin_def: continue
                ctype = self._registry.get(comp.component_type)
                if not ctype: continue

                # Two-terminal loads (buzzer, motor) have no POWER pins but see the rail voltage
                # across them when switched on, so their rating applies to a rail-connected terminal.
                is_load_terminal = (pin_def.direction == PinDirection.PASSIVE
                                    and not any(p.direction == PinDirection.POWER for p in ctype.pins)
                                    and ctype.category in (ComponentCategory.ACTIVE_COMPONENT, ComponentCategory.ACTUATOR))
                if (is_load_terminal or (pin_def.direction == PinDirection.POWER and pin_def.supply != "source")) and \
                        ctype.category not in (ComponentCategory.POWER_SOURCE, ComponentCategory.MICROCONTROLLER):
                    op_v_str = ctype.electrical_properties.get("operating_voltage")
                    if op_v_str:
                        op_range = self._parse_voltage_range(op_v_str)
                        if op_range:
                            min_v, max_v = op_range
                            if net_v < min_v or net_v > max_v:
                                errors.append(ValidationError(
                                    code="E014",
                                    message=f"Component {comp.instance_id} operating voltage ({op_v_str}) is incompatible with net {net.net_id} voltage ({net_v}V)",
                                    severity=ValidationSeverity.ERROR,
                                    affected_instances=[comp.instance_id],
                                    affected_nets=[net.net_id],
                                    validator='design_validator'
                                ))
        return errors

    # ── E015: GPIO Overcurrent ──

    def _parse_current(self, c_str: str) -> float | None:
        import re
        if not c_str: return None
        match = re.search(r"([\d\.]+)\s*(m?A)", str(c_str))
        if match:
            val = float(match.group(1))
            unit = match.group(2)
            if unit == "A":
                return val * 1000.0
            return val # mA
        return None

    def _check_gpio_drive_limit(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        for net in design.nets:
            gpio_max_mA = None
            gpio_pin_ref = None
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if not comp or not pin_def: continue
                ctype = self._registry.get(comp.component_type)
                if not ctype: continue
                if ctype.category == ComponentCategory.MICROCONTROLLER and pin_def.direction in (PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL):
                    c_str = ctype.electrical_properties.get("gpio_max_current")
                    c_val = self._parse_current(c_str)
                    if c_val is not None:
                        gpio_max_mA = c_val
                        gpio_pin_ref = pinref.ref
                        break
            if gpio_max_mA is not None:
                total_load_mA = 0.0
                for pinref in net.connections:
                    if pinref.ref == gpio_pin_ref: continue
                    comp = self._instance_map.get(pinref.instance_id)
                    ctype = self._registry.get(comp.component_type) if comp else None
                    if not ctype: continue

                    load_c_str = ctype.electrical_properties.get("operating_current")
                    # If an actuator doesn't have operating_current, look for alternatives
                    if not load_c_str:
                        load_c_str = ctype.electrical_properties.get("max_current")
                    if not load_c_str:
                        load_c_str = ctype.electrical_properties.get("max_forward_current")

                    load_c = self._parse_current(load_c_str)
                    if load_c is not None:
                        total_load_mA += load_c

                if total_load_mA > gpio_max_mA:
                    errors.append(ValidationError(
                        code="E015",
                        message=f"GPIO {gpio_pin_ref} maximum drive current is {gpio_max_mA}mA, but load draws {total_load_mA}mA",
                        severity=ValidationSeverity.ERROR,
                        affected_pins=[gpio_pin_ref],
                        affected_nets=[net.net_id],
                        validator='design_validator'
                    ))
        return errors

    # ── E016: Missing Power Source ──

    # Two-terminal parts through which a supply rail legitimately continues (power switch,
    # jumper, fuse, series inductor, reverse-polarity diode).
    _SERIES_SUPPLY_FAMILIES = {"switch", "push_button", "jumper", "fuse", "inductor", "diode", "schottky"}

    def _supplied_nets(self, design: EngineeringDesignProject) -> set[str]:
        supplied = {n.net_id for n in design.nets if self._net_has_source(n)}
        changed = True
        while changed:
            changed = False
            for comp in design.components:
                ctype = self._registry.get(comp.component_type)
                if ctype is None or ctype.family not in self._SERIES_SUPPLY_FAMILIES or len(ctype.pins) != 2:
                    continue
                nets = [self._net_of(design, comp.instance_id, p.pin_id) for p in ctype.pins]
                if any(n is None for n in nets):
                    continue
                ids = {n.net_id for n in nets}
                if ids & supplied and not ids <= supplied:
                    if not any(self._net_is_ground(n) for n in nets):
                        supplied |= ids
                        changed = True
        return supplied

    def _check_missing_power_source(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        supplied = self._supplied_nets(design)
        for net in design.nets:
            if net.net_id in supplied:
                continue
            has_power_pin = False
            has_valid_source = False

            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if not comp or not pin_def: continue
                ctype = self._registry.get(comp.component_type)
                if not ctype: continue

                if pin_def.direction == PinDirection.POWER:
                    has_power_pin = True
                    if self._source_voltage(pinref.instance_id, pinref.pin_id)[0]:
                        has_valid_source = True
                    elif ctype.category == ComponentCategory.MICROCONTROLLER and pin_def.supply is None:
                        mcu_op_v_str = ctype.electrical_properties.get("operating_voltage", "")
                        mcu_op_range = self._parse_voltage_range(mcu_op_v_str)
                        if mcu_op_range:
                            mcu_op_v = mcu_op_range[0]
                            pin_v = self._parse_voltage(pin_def.electrical_type)
                            if pin_v is None:
                                pin_v = pin_def.max_voltage
                            if pin_v == mcu_op_v:
                                has_valid_source = True

            if has_power_pin and not has_valid_source:
                errors.append(ValidationError(
                    code="E016",
                    message=f"Net {net.net_id} contains POWER pins but has no valid power source (e.g. power rail or MCU regulated output)",
                    severity=ValidationSeverity.ERROR,
                    affected_nets=[net.net_id],
                    validator='design_validator'
                ))
        return errors

    # ── E010: Voltage incompatibility ──

    def _check_voltage_compatibility(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """For each net, check that no OUTPUT/BIDIRECTIONAL pin's min_voltage
        exceeds any INPUT/BIDIRECTIONAL pin's max_voltage on the same net.

        If a pin lacks voltage metadata, this check is skipped for that pair
        (handled by W002 instead). A missing check never becomes a silent PASS.

        Passive pins (resistors) are transparent to this check — they do not
        produce or consume voltage levels, so they are skipped. This is correct
        because a resistor divider reduces voltage; the validator checks the
        actual endpoint voltages, not intermediate passives.
        """
        errors = []
        for net in design.nets:
            # Collect output-capable pins and input-capable pins on this net
            output_pins: list[tuple[str, PinDefinition]] = []  # (pinref_str, pin_def)
            input_pins: list[tuple[str, PinDefinition]] = []

            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def is None:
                    continue

                # Skip PASSIVE, POWER, GROUND — they don't have logic-level semantics
                if pin_def.direction in (PinDirection.PASSIVE, PinDirection.POWER, PinDirection.GROUND):
                    continue

                # Open-drain buses (I2C) do not drive a voltage level: the pull-up does.
                open_drain = (pin_def.electrical_type or "").upper() in ("I2C", "OPEN_DRAIN", "OPEN_COLLECTOR")
                if pin_def.direction in (PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL) and not open_drain:
                    output_pins.append((pinref.ref, pin_def))
                if pin_def.direction in (PinDirection.INPUT, PinDirection.BIDIRECTIONAL):
                    input_pins.append((pinref.ref, pin_def))

            # Check each output→input pair
            for out_ref, out_def in output_pins:
                out_voltage = out_def.max_voltage
                if out_voltage is None:
                    continue  # No voltage data → W002, not E010

                for in_ref, in_def in input_pins:
                    if out_ref == in_ref:
                        continue  # Same pin (bidirectional) — skip self-check
                    in_max = in_def.max_voltage
                    if in_max is None:
                        continue  # No voltage data → W002

                    if out_voltage > in_max:
                        errors.append(ValidationError(
                            code="E010",
                            message=(
                                f"Voltage incompatibility on net {net.net_id}: "
                                f"{out_ref} outputs up to {out_voltage}V "
                                f"but {in_ref} tolerates max {in_max}V"
                            ),
                            severity=ValidationSeverity.ERROR,
                            affected_pins=[out_ref, in_ref],
                            affected_nets=[net.net_id],
                            validator='design_validator'
                        ))
        return errors

    # ── E011: Short circuit (POWER ↔ GROUND on same net) ──

    def _check_short_circuit(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """Detect nets that directly connect a POWER pin to a GROUND pin
        without any intermediate passive component (resistor, load, etc.).

        A net with both a POWER-direction pin and a GROUND-direction pin
        AND no PASSIVE-direction pin in between is flagged as a short circuit.
        """
        errors = []
        for net in design.nets:
            has_power = False
            has_ground = False
            has_passive_or_load = False

            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def is None:
                    continue
                if pin_def.direction == PinDirection.POWER:
                    has_power = True
                elif pin_def.direction == PinDirection.GROUND:
                    has_ground = True
                elif pin_def.direction in (PinDirection.PASSIVE, PinDirection.INPUT,
                                           PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL):
                    has_passive_or_load = True

            if has_power and has_ground and not has_passive_or_load:
                errors.append(ValidationError(
                    code="E011",
                    message=f"Short circuit: net {net.net_id} connects POWER directly to GROUND with no load",
                    severity=ValidationSeverity.ERROR,
                    affected_nets=[net.net_id],
                    validator='design_validator'
                ))
        return errors

    # ── E012: Logic Invalid Instance ──

    def _check_logic_instances(self, design: EngineeringDesignProject) -> list[ValidationError]:
        errors = []
        for rule in design.logic:
            for cond in rule.conditions:
                if cond.input_instance not in self._instance_map:
                    errors.append(ValidationError(
                        code="E012",
                        message=f"Logic rule '{rule.rule_id}' references unknown input instance: {cond.input_instance}",
                        severity=ValidationSeverity.ERROR,
                        affected_instances=[cond.input_instance],
                        validator='design_validator'
                    ))
            for act in rule.actions:
                if act.output_instance not in self._instance_map:
                    errors.append(ValidationError(
                        code="E012",
                        message=f"Logic rule '{rule.rule_id}' references unknown output instance: {act.output_instance}",
                        severity=ValidationSeverity.ERROR,
                        affected_instances=[act.output_instance],
                        validator='design_validator'
                    ))
        return errors

    # ── Constraint-driven checks (E017/W005, E018, W003, W004, W006) ──

    def _constraints(self, design, kind: str):
        for comp in design.components:
            ctype = self._registry.get(comp.component_type)
            if ctype is None:
                continue
            for c in ctype.design_constraints:
                if c.kind == kind:
                    yield comp, ctype, c

    @staticmethod
    def _severity(c) -> ValidationSeverity:
        return {"ERROR": ValidationSeverity.ERROR, "WARNING": ValidationSeverity.WARNING}.get(c.severity, ValidationSeverity.INFO)

    def _check_flyback(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """Inductive loads need a diode across their terminals (A on one net, K on the other),
        unless a driver on those nets declares integrated clamp diodes."""
        out = []
        items = list(self._constraints(design, "flyback_diode"))
        if not items:
            self._not_applicable.add("_check_flyback")
        for comp, ctype, c in items:
            if len(c.pins) != 2:
                continue
            n1 = self._net_of(design, comp.instance_id, c.pins[0])
            n2 = self._net_of(design, comp.instance_id, c.pins[1])
            if n1 is None or n2 is None:
                continue  # an unconnected coil is E009's business
            ids1 = {pr.instance_id for pr in n1.connections}
            ids2 = {pr.instance_id for pr in n2.connections}
            clamped = False
            for other in ids1 & ids2:
                octype = self._ctype_of(other)
                if octype and octype.family in ("diode", "schottky"):
                    clamped = True
            for other in ids1 | ids2:
                octype = self._ctype_of(other)
                if octype and "integrated clamp diodes" in octype.tags:
                    clamped = True
            if not clamped:
                sev = self._severity(c)
                out.append(ValidationError(
                    code="E017" if sev == ValidationSeverity.ERROR else "W005",
                    message=f"{comp.instance_id} ({ctype.name}) is inductive and has no flyback diode across {c.pins[0]}/{c.pins[1]}. {c.note}".strip(),
                    severity=sev if sev != ValidationSeverity.INFO else ValidationSeverity.WARNING,
                    affected_instances=[comp.instance_id], affected_nets=[n1.net_id, n2.net_id],
                    validator='constraint_validator'))
        return out

    _POLAR_SYMBOLS = {"led": ("A", "K"), "diode": ("A", "K"), "schottky": ("A", "K"), "capacitor_polarized": ("+", "-")}

    def _check_polarity(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """A polarised part with its anode/+ on ground and cathode/- on a supply rail is reversed
        (a diode there would also short the supply)."""
        out = []
        any_polar = False
        for comp in design.components:
            ctype = self._registry.get(comp.component_type)
            if ctype is None or ctype.symbol is None or ctype.symbol.name not in self._POLAR_SYMBOLS:
                continue
            any_polar = True
            pos_sym, neg_sym = self._POLAR_SYMBOLS[ctype.symbol.name]
            inv = {v: k for k, v in ctype.symbol.pin_map.items()}
            pos_pin, neg_pin = inv.get(pos_sym, pos_sym), inv.get(neg_sym, neg_sym)
            n_pos = self._net_of(design, comp.instance_id, pos_pin)
            n_neg = self._net_of(design, comp.instance_id, neg_pin)
            if n_pos is None or n_neg is None:
                continue
            if self._net_is_ground(n_pos) and self._net_is_supply(n_neg):
                out.append(ValidationError(
                    code="E018",
                    message=f"{comp.instance_id} ({ctype.name}) is reversed: {pos_pin} is on ground net {n_pos.net_id} and {neg_pin} on supply net {n_neg.net_id}",
                    severity=ValidationSeverity.ERROR, affected_instances=[comp.instance_id],
                    affected_pins=[f"{comp.instance_id}.{pos_pin}", f"{comp.instance_id}.{neg_pin}"],
                    affected_nets=[n_pos.net_id, n_neg.net_id], validator='constraint_validator'))
        if not any_polar:
            self._not_applicable.add("_check_polarity")
        return out

    def _check_series_constraints(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """Non-ERROR series_resistor constraints (ERROR ones are enforced by E007)."""
        out = []
        items = [(comp, ct, c) for comp, ct, c in self._constraints(design, "series_resistor") if c.severity != "ERROR"]
        if not items:
            self._not_applicable.add("_check_series_constraints")
        for comp, ctype, c in items:
            for pin in c.pins:
                net = self._net_of(design, comp.instance_id, pin)
                if net is None:
                    continue
                if not any(self._is_resistor(pr.instance_id) for pr in net.connections if pr.instance_id != comp.instance_id):
                    out.append(ValidationError(
                        code="W003", message=f"{comp.instance_id}.{pin}: no series resistor on net {net.net_id}. {c.note}".strip(),
                        severity=self._severity(c), affected_instances=[comp.instance_id],
                        affected_pins=[f"{comp.instance_id}.{pin}"], affected_nets=[net.net_id], validator='constraint_validator'))
        return out

    def _check_pullups(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """Each constrained pin's net needs a resistor whose other end is on a supply rail."""
        out = []
        items = list(self._constraints(design, "pullup_required"))
        if not items:
            self._not_applicable.add("_check_pullups")
        for comp, ctype, c in items:
            for pin in c.pins:
                net = self._net_of(design, comp.instance_id, pin)
                if net is None:
                    continue
                ok = False
                for pr in net.connections:
                    if pr.instance_id == comp.instance_id or not self._is_resistor(pr.instance_id):
                        continue
                    rtype = self._ctype_of(pr.instance_id)
                    for other_pin in (p.pin_id for p in rtype.pins if p.pin_id != pr.pin_id):
                        other_net = self._net_of(design, pr.instance_id, other_pin)
                        if other_net is not None and self._net_is_supply(other_net):
                            ok = True
                if not ok:
                    value = f" (typically {c.value})" if c.value else ""
                    out.append(ValidationError(
                        code="W004", message=f"{comp.instance_id}.{pin} on net {net.net_id} has no pull-up resistor to a supply{value}. {c.note}".strip(),
                        severity=self._severity(c), affected_instances=[comp.instance_id],
                        affected_pins=[f"{comp.instance_id}.{pin}"], affected_nets=[net.net_id], validator='constraint_validator'))
        return out

    def _check_decoupling(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """A capacitor must bridge the constrained supply pin's net and a ground net."""
        out = []
        items = list(self._constraints(design, "decoupling_capacitor"))
        if not items:
            self._not_applicable.add("_check_decoupling")
        for comp, ctype, c in items:
            for pin in c.pins:
                net = self._net_of(design, comp.instance_id, pin)
                if net is None:
                    continue
                ok = False
                for pr in net.connections:
                    octype = self._ctype_of(pr.instance_id)
                    if octype is None or octype.family != "capacitor":
                        continue
                    for other_pin in (p.pin_id for p in octype.pins if p.pin_id != pr.pin_id):
                        other_net = self._net_of(design, pr.instance_id, other_pin)
                        if other_net is not None and self._net_is_ground(other_net):
                            ok = True
                if not ok:
                    value = f" ({c.value})" if c.value else ""
                    out.append(ValidationError(
                        code="W006", message=f"{comp.instance_id}.{pin}: no decoupling capacitor{value} to ground. {c.note}".strip(),
                        severity=self._severity(c), affected_instances=[comp.instance_id],
                        affected_pins=[f"{comp.instance_id}.{pin}"], affected_nets=[net.net_id], validator='constraint_validator'))
        return out

    def _connected_pins(self, design) -> set[str]:
        return {pr.ref for net in design.nets for pr in net.connections}

    def _check_source_return(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """A battery / supply whose + terminal feeds a net but whose - terminal goes nowhere
        cannot deliver current: every load on that rail is dead."""
        out = []
        connected = self._connected_pins(design)
        any_source = False
        for comp in design.components:
            ctype = self._registry.get(comp.component_type)
            if ctype is None:
                continue
            sources = [p for p in ctype.pins if self._source_voltage(comp.instance_id, p.pin_id)[0]]
            grounds = [p for p in ctype.pins if p.direction == PinDirection.GROUND]
            if not sources or not grounds or ctype.category == ComponentCategory.MICROCONTROLLER:
                continue  # boards expose extra supply pins but are powered through their own inputs
            any_source = True
            fed = [p for p in sources if f"{comp.instance_id}.{p.pin_id}" in connected]
            returns = [p for p in grounds if f"{comp.instance_id}.{p.pin_id}" in connected]
            if fed and not returns:
                out.append(ValidationError(
                    code="E019",
                    message=f"{comp.instance_id} ({ctype.name}) supplies {', '.join(p.pin_id for p in fed)} but its "
                            f"{'/'.join(p.pin_id for p in grounds)} terminal is not connected - there is no current return path",
                    severity=ValidationSeverity.ERROR, affected_instances=[comp.instance_id],
                    affected_pins=[f"{comp.instance_id}.{p.pin_id}" for p in grounds], validator='design_validator'))
        if not any_source:
            self._not_applicable.add("_check_source_return")
        return out

    def _check_supply_inputs(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """Warn when a part that needs supply has none of its supply-input pins connected."""
        out = []
        connected = self._connected_pins(design)
        for comp in design.components:
            ctype = self._registry.get(comp.component_type)
            if ctype is None:
                continue
            power = [p for p in ctype.pins if p.direction == PinDirection.POWER]
            sinks = [p for p in power if not self._source_voltage(comp.instance_id, p.pin_id)[0]]
            if not sinks:
                continue
            if any(f"{comp.instance_id}.{p.pin_id}" in connected for p in power):
                continue
            if not any(f"{comp.instance_id}.{p.pin_id}" in connected for p in ctype.pins):
                continue  # completely unconnected parts are reported by E009
            extra = (" A development board can be powered from USB; if that is intended, record it as an assumption."
                     if ctype.category == ComponentCategory.MICROCONTROLLER else "")
            out.append(ValidationError(
                code="W007",
                message=f"{comp.instance_id} ({ctype.name}) has no supply connection ({', '.join(p.pin_id for p in sinks)} unconnected).{extra}",
                severity=ValidationSeverity.WARNING, affected_instances=[comp.instance_id],
                affected_pins=[f"{comp.instance_id}.{p.pin_id}" for p in sinks], validator='design_validator'))
        return out

    # ── W001: Missing resistor value ──

    def _check_resistor_parameters(self, design: EngineeringDesignProject) -> list[ValidationError]:
        warnings = []
        for comp in design.components:
            if comp.component_type.startswith('passive:resistor'):
                if not comp.parameters or 'resistance' not in comp.parameters:
                    warnings.append(ValidationError(
                        code="W001",
                        message=f"Resistor {comp.instance_id} is missing 'resistance' parameter",
                        severity=ValidationSeverity.WARNING,
                        affected_instances=[comp.instance_id],
                        validator='design_validator'
                    ))
        return warnings

    # ── W002: Voltage metadata missing ──

    def _check_voltage_metadata_coverage(self, design: EngineeringDesignProject) -> list[ValidationError]:
        """Emit W002 for any signal pin (INPUT/OUTPUT/BIDIRECTIONAL) that
        lacks max_voltage. This ensures missing metadata is surfaced rather
        than silently treated as passing."""
        warnings = []
        seen: set[str] = set()

        for net in design.nets:
            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def is None:
                    continue
                ctype = self._ctype_of(pinref.instance_id)
                if ctype is not None and ctype.object_type != ObjectType.PHYSICAL:
                    continue  # idealised primitives have no physical voltage limits by definition
                if pin_def.direction in (PinDirection.INPUT, PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL):
                    if pin_def.max_voltage is None and pinref.ref not in seen:
                        seen.add(pinref.ref)
                        warnings.append(ValidationError(
                            code="W002",
                            message=(
                                f"Voltage metadata missing for {pinref.ref}: "
                                f"cannot verify voltage compatibility"
                            ),
                            severity=ValidationSeverity.WARNING,
                            affected_pins=[pinref.ref],
                            affected_nets=[net.net_id],
                            validator='design_validator'
                        ))
        return warnings