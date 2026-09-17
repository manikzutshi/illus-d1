from core.models import DesignProject, ValidationResult, ValidationError
from core.enums import ValidationStatus, ValidationSeverity, PinDirection
from components.registry import ComponentRegistry

class DesignValidator:
    """Deterministic validator for DesignProject instances.
    Does NOT use any LLM. All rules are explicit."""
    
    def __init__(self, registry: ComponentRegistry):
        self._registry = registry
    
    def validate(self, design: DesignProject) -> ValidationResult:
        """Run all validation checks and return a deterministic result."""
        errors = []
        warnings = []
        
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
        warnings.extend(self._check_resistor_parameters(design))
        
        status = ValidationStatus.FAIL if errors else ValidationStatus.PASS
        return ValidationResult(
            status=status,
            errors=errors,
            warnings=warnings,
            component_count=len(design.components),
            net_count=len(design.nets)
        )

    def _check_unknown_components(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        for comp in design.components:
            if not self._registry.has(comp.component_type):
                errors.append(ValidationError(
                    code="E001",
                    message=f"Unknown component type: {comp.component_type}",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=[comp.instance_id],
                    affected_pins=[],
                    affected_nets=[],
                    validator='design_validator'
                ))
        return errors

    def _check_duplicate_instances(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        seen = set()
        for comp in design.components:
            if comp.instance_id in seen:
                errors.append(ValidationError(
                    code="E003",
                    message=f"Duplicate instance ID: {comp.instance_id}",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=[comp.instance_id],
                    affected_pins=[],
                    affected_nets=[],
                    validator='design_validator'
                ))
            seen.add(comp.instance_id)
        return errors

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

    def _check_dangling_power(self, design: DesignProject) -> list[ValidationError]:
        has_power = False
        for net in design.nets:
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                if comp and self._registry.has(comp.component_type):
                    ctype = self._registry.get(comp.component_type)
                    pin_def = next((p for p in ctype.pins if p.pin_id == pinref.pin_id), None)
                    if pin_def and pin_def.direction == PinDirection.POWER:
                        has_power = True
                        break
            if has_power:
                break
        
        if not has_power and design.components:
            return [ValidationError(
                code="E004",
                message="No connected POWER pins found in any net.",
                severity=ValidationSeverity.ERROR,
                affected_instances=[],
                affected_pins=[],
                affected_nets=[],
                validator='design_validator'
            )]
        return []

    def _check_dangling_ground(self, design: DesignProject) -> list[ValidationError]:
        has_ground = False
        for net in design.nets:
            for pinref in net.connections:
                comp = self._instance_map.get(pinref.instance_id)
                if comp and self._registry.has(comp.component_type):
                    ctype = self._registry.get(comp.component_type)
                    pin_def = next((p for p in ctype.pins if p.pin_id == pinref.pin_id), None)
                    if pin_def and pin_def.direction == PinDirection.GROUND:
                        has_ground = True
                        break
            if has_ground:
                break
        
        if not has_ground and design.components:
            return [ValidationError(
                code="E005",
                message="No connected GROUND pins found in any net.",
                severity=ValidationSeverity.ERROR,
                affected_instances=[],
                affected_pins=[],
                affected_nets=[],
                validator='design_validator'
            )]
        return []

    def _check_invalid_connections(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        for net in design.nets:
            for pinref in net.connections:
                if pinref.instance_id not in self._instance_map:
                    errors.append(ValidationError(
                        code="E006",
                        message=f"PinRef refers to unknown instance ID: {pinref.instance_id}",
                        severity=ValidationSeverity.ERROR,
                        affected_instances=[],
                        affected_pins=[pinref.ref],
                        affected_nets=[net.net_id],
                        validator='design_validator'
                    ))
        return errors

    def _check_led_resistor(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        # Find all nets that have a resistor connected
        resistor_nets = set()
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
                        affected_pins=[],
                        affected_nets=[],
                        validator='design_validator'
                    ))
        return errors

    def _check_duplicate_nets(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        seen = set()
        for net in design.nets:
            if net.net_id in seen:
                errors.append(ValidationError(
                    code="E008",
                    message=f"Duplicate net ID: {net.net_id}",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=[],
                    affected_pins=[],
                    affected_nets=[net.net_id],
                    validator='design_validator'
                ))
            seen.add(net.net_id)
        return errors

    def _check_disconnected_components(self, design: DesignProject) -> list[ValidationError]:
        errors = []
        connected_instances = set()
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
                    affected_pins=[],
                    affected_nets=[],
                    validator='design_validator'
                ))
        return errors

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
                        affected_pins=[],
                        affected_nets=[],
                        validator='design_validator'
                    ))
        return warnings
