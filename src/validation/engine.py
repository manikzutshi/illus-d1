"""Deterministic validation engine for DesignProject instances.

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

Warning codes:
    W001  MISSING_RESISTOR_VALUE       Resistor instance has no 'resistance' parameter
    W002  VOLTAGE_NOT_CHECKABLE        Voltage metadata missing; cannot verify compatibility

All rules are deterministic. No LLM dependency.
"""
from core.models import DesignProject, ValidationResult, ValidationError, PinDefinition
from core.enums import ValidationStatus, ValidationSeverity, PinDirection
from components.registry import ComponentRegistry


class DesignValidator:
    """Deterministic validator for DesignProject instances.
    Does NOT use any LLM. All rules are explicit."""

    def __init__(self, registry: ComponentRegistry):
        self._registry = registry

    def validate(self, design: DesignProject) -> ValidationResult:
        """Run all validation checks and return a deterministic result."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Build lookup dictionaries for efficiency
        self._instance_map = {comp.instance_id: comp for comp in design.components}

        # Run each check, collecting errors/warnings
        errors.extend(self._check_unknown_components(design))
        errors.extend(self._check_duplicate_instances(design))
        errors.extend(self._check_unknown_pins(design))
        errors.extend(self._check_dangling_power(design))
        errors.extend(self._check_dangling_ground(design))
        errors.extend(self._check_invalid_connections(design))
        errors.extend(self._check_led_resistor(design))
        errors.extend(self._check_duplicate_nets(design))
        errors.extend(self._check_disconnected_components(design))
        errors.extend(self._check_voltage_compatibility(design))
        errors.extend(self._check_short_circuit(design))
        warnings.extend(self._check_resistor_parameters(design))
        warnings.extend(self._check_voltage_metadata_coverage(design))

        status = ValidationStatus.FAIL if errors else ValidationStatus.PASS
        return ValidationResult(
            status=status,
            errors=errors,
            warnings=warnings,
            component_count=len(design.components),
            net_count=len(design.nets)
        )

    # ── Helpers ─────────────────────────────────────────────────────────

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

    # ── E001: Unknown component type ────────────────────────────────────

    def _check_unknown_components(self, design: DesignProject) -> list[ValidationError]:
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

    # ── E002: Unknown pin ───────────────────────────────────────────────

    def _check_unknown_pins(self, design: DesignProject) -> list[ValidationError]:
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

    # ── E003: Duplicate instance ID ─────────────────────────────────────

    def _check_duplicate_instances(self, design: DesignProject) -> list[ValidationError]:
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

    # ── E004: Missing power ─────────────────────────────────────────────

    def _check_dangling_power(self, design: DesignProject) -> list[ValidationError]:
        for net in design.nets:
            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def and pin_def.direction == PinDirection.POWER:
                    return []
        if design.components:
            return [ValidationError(
                code="E004",
                message="No connected POWER pins found in any net.",
                severity=ValidationSeverity.ERROR,
                validator='design_validator'
            )]
        return []

    # ── E005: Missing ground ────────────────────────────────────────────

    def _check_dangling_ground(self, design: DesignProject) -> list[ValidationError]:
        for net in design.nets:
            for pinref in net.connections:
                pin_def = self._resolve_pin_def(pinref.instance_id, pinref.pin_id)
                if pin_def and pin_def.direction == PinDirection.GROUND:
                    return []
        if design.components:
            return [ValidationError(
                code="E005",
                message="No connected GROUND pins found in any net.",
                severity=ValidationSeverity.ERROR,
                validator='design_validator'
            )]
        return []

    # ── E006: Invalid connection endpoint ───────────────────────────────

    def _check_invalid_connections(self, design: DesignProject) -> list[ValidationError]:
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

    # ── E007: LED requires resistor ─────────────────────────────────────

    def _check_led_resistor(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        # Find all nets that have a resistor connected
        resistor_nets: set[str] = set()
        for net in design.nets:
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                if comp and 'resistor' in comp.component_type.lower():
                    resistor_nets.add(net.net_id)
                    break

        for comp in design.components:
            if 'led' in comp.component_type.lower():
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

    # ── E008: Duplicate net ID ──────────────────────────────────────────

    def _check_duplicate_nets(self, design: DesignProject) -> list[ValidationError]:
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

    # ── E009: Disconnected component ────────────────────────────────────

    def _check_disconnected_components(self, design: DesignProject) -> list[ValidationError]:
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

    # ── E010: Voltage incompatibility ───────────────────────────────────

    def _check_voltage_compatibility(self, design: DesignProject) -> list[ValidationError]:
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

                if pin_def.direction in (PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL):
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

    # ── E011: Short circuit (POWER ↔ GROUND on same net) ────────────────

    def _check_short_circuit(self, design: DesignProject) -> list[ValidationError]:
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

    # ── W001: Missing resistor value ────────────────────────────────────

    def _check_resistor_parameters(self, design: DesignProject) -> list[ValidationError]:
        warnings = []
        for comp in design.components:
            if 'resistor' in comp.component_type.lower():
                if not comp.parameters or 'resistance' not in comp.parameters:
                    warnings.append(ValidationError(
                        code="W001",
                        message=f"Resistor {comp.instance_id} is missing 'resistance' parameter",
                        severity=ValidationSeverity.WARNING,
                        affected_instances=[comp.instance_id],
                        validator='design_validator'
                    ))
        return warnings

    # ── W002: Voltage metadata missing ──────────────────────────────────

    def _check_voltage_metadata_coverage(self, design: DesignProject) -> list[ValidationError]:
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
