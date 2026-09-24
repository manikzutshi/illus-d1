# First Implementation Task: Illustration Engine

This document identifies a single concrete first implementation task that would provide immediate value while demonstrating progress toward the target smart GenAI electronics illustrator architecture.

## Selected Task: Implement Design Session Management with CLI Visualization Integration

**Task Description**: Add basic design session management capabilities to the CLI and integrate with the existing visualizer to allow users to run AI-assisted design sessions and visualize the results.

### Why This Task?

This task was selected because it:
1. **Delivers Immediate Value**: Users can immediately benefit from iterative AI-assisted design with visual feedback
2. **Demonstrates Architectural Progress**: Shows movement toward the target architecture's session management and visualization layers
3. **Builds on Existing Foundation**: Uses existing AI orchestrator, validation engine, and visualizer components
4. **Enables Future Work**: Provides the foundation for more advanced features in later phases
5. **Has Clear Boundaries**: Well-defined scope that can be completed in a reasonable timeframe
6. **Addresses Current Limitations**: Fixes the lack of iterative design capability and visual feedback

## Detailed Task Breakdown

### Component 1: Design Session Management (`src/ai/session.py`)

Create a new module to manage design session state:

```python
# src/ai/session.py
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4
from ..core.models import DesignProject, ValidationResult
from ..ai.orchestrator import Orchestrator, OrchestratorConfig

class DesignSession:
    """Manages a single design session with state persistence."""
    
    def __init__(self, session_id: str, orchestrator: Orchestrator):
        self.session_id = session_id
        self.orchestrator = orchestrator
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.history: List[Dict[str, Any]] = []
        self.current_design: Optional[DesignProject] = None
        self.validation_history: List[ValidationResult] = []
        
    def add_interaction(self, 
                       user_input: str, 
                       ai_response: str, 
                       design: Optional[DesignProject] = None,
                       validation: Optional[ValidationResult] = None):
        """Record an interaction in the session history."""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "ai_response": ai_response,
            "design": design.dict() if design else None,
            "validation": validation.dict() if validation else None
        }
        self.history.append(interaction)
        self.updated_at = datetime.now()
        
        if design:
            self.current_design = design
        if validation:
            self.validation_history.append(validation)
            
    def get_context(self, max_interactions: int = 5) -> str:
        """Get recent conversation history for context."""
        recent = self.history[-max_interactions:] if self.history else []
        context_parts = []
        for interaction in recent:
            context_parts.append(f"User: {interaction['user_input']}")
            context_parts.append(f"Assistant: {interaction['ai_response']}")
        return "\n".join(context_parts)
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "history": self.history,
            "current_design": self.current_design.dict() if self.current_design else None,
            "validation_count": len(self.validation_history)
        }

class SessionManager:
    """Manages multiple design sessions."""
    
    def __init__(self):
        self.sessions: Dict[str, DesignSession] = {}
        
    def create_session(self, provider_type: str = "mock") -> DesignSession:
        """Create a new design session."""
        from ..ai.provider import ProviderType
        from ..ai.orchestrator import OrchestratorConfig
        
        # Map string to ProviderType
        provider_map = {
            "mock": ProviderType.MOCK,
            "gemini": ProviderType.GEMINI,
            "openai": ProviderType.OPENAI
        }
        provider_enum = provider_map.get(provider_type.lower(), ProviderType.MOCK)
        
        config = OrchestratorConfig(provider_type=provider_enum)
        orchestrator = Orchestrator(config)
        session_id = str(uuid4())
        
        session = DesignSession(session_id, orchestrator)
        self.sessions[session_id] = session
        return session
        
    def get_session(self, session_id: str) -> Optional[DesignSession]:
        """Retrieve a session by ID."""
        return self.sessions.get(session_id)
        
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions with summary info."""
        return [
            {
                "session_id": sid,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "interaction_count": len(session.history),
                "has_current_design": session.current_design is not None
            }
            for sid, session in self.sessions.items()
        ]
        
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
```

### Component 2: Enhanced CLI Commands (`src/cli/main.py` modifications)

Add new CLI commands for session management and visualization:

```python
# Add to existing CLI commands in src/cli/main.py

@app.command()
def agent_run(
    requirement: str = typer.Argument(..., help="Design requirement description"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to continue"),
    provider: str = typer.Option("mock", "--provider", "-p", help="AI provider to use (mock, gemini, openai)"),
    max_iterations: int = typer.Option(5, "--max-iterations", "-m", help="Maximum optimization iterations"),
    visualize: bool = typer.Option(False, "--visualize", "-v", help="Launch visualizer after completion")
):
    """Run AI-assisted design session with iterative improvement."""
    try:
        # Initialize session manager
        from ..ai.session import SessionManager
        session_manager = SessionManager()
        
        # Get or create session
        if session_id:
            session = session_manager.get_session(session_id)
            if not session:
                console.print(f"[red]Error: Session {session_id} not found[/red]")
                raise typer.Exit(code=1)
        else:
            session = session_manager.create_session(provider)
            console.print(f"[green]Created new session: {session.session_id}[/green]")
        
        # Run orchestrator with session context
        console.print(f"[blue]Processing requirement:[/blue] {requirement}")
        
        # Add user input to session history
        session.add_interaction(
            user_input=requirement,
            ai_response="Processing requirement..."
        )
        
        # Run the orchestrator (would need modification to accept session context)
        # For now, using existing orchestrator but we'd enhance it to use session context
        orchestrator = session.orchestrator
        
        # Execute design generation with validation loop
        result = orchestrator.run_design_loop(
            requirement=requirement,
            max_iterations=max_iterations,
            session_context=session.get_context()
        )
        
        # Update session with results
        if result.design:
            session.add_interaction(
                user_input=requirement,
                ai_response=f"Generated design with {len(result.design.components)} components",
                design=result.design,
                validation=result.validation_result
            )
        
        # Display results
        console.print(f"[green]Session ID:[/green] {session.session_id}")
        console.print(f"[blue]Components:[/blue] {len(result.design.components) if result.design else 0}")
        console.print(f"[blue]Nets:[/blue] {len(result.design.nets) if result.design else 0}")
        
        if result.validation_result:
            status_color = "green" if result.validation_result.status == "PASS" else "red"
            console.print(f"[{status_color}]Validation:[/]{status_color} {result.validation_result.status}[/{status_color}]")
            if result.validation_result.errors:
                console.print(f"[red]Errors ({len(result.validation_result.errors)}):[/red]")
                for error in result.validation_result.errors[:3]:  # Show first 3 errors
                    console.print(f"  • {error.summary}")
        
        # Handle visualization
        if visualize and result.design:
            console.print("[yellow]Launching visualizer...[/yellow]")
            # In a real implementation, this would launch the visualizer with the design data
            # For now, we'll indicate where this would happen
            console.print("[dim]Note: Visualizer integration would launch here in full implementation[/dim]")
            
        # Show session info for continuation
        console.print(f"\n[dim]Continue this session with: illustration-engine agent-run --session {session.session_id} \"your next requirement\"[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

@app.command()
def session_list():
    """List all design sessions."""
    try:
        from ..ai.session import SessionManager
        session_manager = SessionManager()
        sessions = session_manager.list_sessions()
        
        if not sessions:
            console.print("[yellow]No design sessions found[/yellow]")
            return
            
        table = Table(title="Design Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Created", style="green")
        table.add_column("Updated", style="green")
        table.add_column("Interactions", justify="right")
        table.add_column("Has Design", justify="right")
        
        for session in sessions:
            table.add_row(
                session["session_id"][:8] + "...",  # Truncate for display
                session["created_at"][:19],  # Trim to seconds
                session["updated_at"][:19],
                str(session["interaction_count"]),
                "✓" if session["has_current_design"] else "✗"
            )
            
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

@app.command()
def session_show(
    session_id: str = typer.Argument(..., help="Session ID to show")
):
    """Show details of a specific design session."""
    try:
        from ..ai.session import SessionManager
        session_manager = SessionManager()
        session = session_manager.get_session(session_id)
        
        if not session:
            console.print(f"[red]Error: Session {session_id} not found[/red]")
            raise typer.Exit(code=1)
            
        console.print(f"[blue]Session Details:[/blue] {session.session_id}")
        console.print(f"Created: {session.created_at}")
        console.print(f"Updated: {session.updated_at}")
        console.print(f"Interactions: {len(session.history)}")
        console.print(f"Validations: {len(session.validation_history)}")
        
        if session.current_design:
            console.print(f"Current Design: {len(session.current_design.components)} components, {len(session.current_design.nets)} nets")
        else:
            console.print("Current Design: None")
            
        # Show recent history
        if session.history:
            console.print("\n[blue]Recent History:[/blue]")
            for i, interaction in enumerate(session.history[-3:], 1):  # Last 3 interactions
                console.print(f"\n{i}. [{interaction['timestamp'][:19]}]")
                console.print(f"   User: {interaction['user_input'][:100]}{'...' if len(interaction['user_input']) > 100 else ''}")
                console.print(f"   Assistant: {interaction['ai_response'][:100]}{'...' if len(interaction['ai_response']) > 100 else ''}")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

@app.command()
def visualize(
    session_id: str = typer.Argument(..., help="Session ID to visualize"),
    design_file: Optional[str] = typer.Option(None, "--design", "-d", help="Path to design JSON file (alternative to session)")
):
    """Visualize a design from a session or file."""
    try:
        if design_file:
            # Load design from file
            import json
            from pathlib import Path
            from ..core.models import DesignProject
            
            design_path = Path(design_file)
            if not design_path.exists():
                console.print(f"[red]Error: Design file {design_file} not found[/red]")
                raise typer.Exit(code=1)
                
            with open(design_path) as f:
                design_data = json.load(f)
            design = DesignProject(**design_data)
            console.print(f"[green]Loaded design from {design_file}[/green]")
        else:
            # Load design from session
            from ..ai.session import SessionManager
            session_manager = SessionManager()
            session = session_manager.get_session(session_id)
            
            if not session:
                console.print(f"[red]Error: Session {session_id} not found[/red]")
                raise typer.Exit(code=1)
                
            if not session.current_design:
                console.print(f"[red]Error: Session {session_id} has no design to visualize[/red]")
                raise typer.Exit(code=1)
                
            design = session.current_design
            console.print(f"[green]Loaded design from session {session_id}[/green]")
        
        # In a real implementation, this would launch the visualizer
        # For now, we'll show what would happen and display design summary
        console.print("[yellow]Preparing design for visualization...[/yellow]")
        console.print(f"[blue]Design Summary:[/blue]")
        console.print(f"  • Components: {len(design.components)}")
        console.print(f"  • Nets: {len(design.nets)}")
        
        if design.components:
            console.print("\n[blue]Components:[/blue]")
            for comp in design.components[:5]:  # Show first 5 components
                console.print(f"  • {comp.instance_id}: {comp.component_type}")
                if comp.properties:
                    props_str = ", ".join([f"{k}={v}" for k, v in list(comp.properties.items())[:3]])
                    console.print(f"    Properties: {props_str}")
            if len(design.components) > 5:
                console.print(f"  • ... and {len(design.components) - 5} more")
        
        console.print("\n[dim]Note: In full implementation, this would launch the visualizer GUI[/dim]")
        console.print("[dim]Visualizer would show: schematic layout, component properties, validation overlays[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
```

### Component 3: Enhanced Orchestrator Context Support

Modify the orchestrator to accept and use session context:

```python
# Modification to src/ai/orchestrator.py - add context support to run_design_loop

async def run_design_loop(
    self, 
    requirement: str, 
    max_iterations: int = 5,
    session_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the AI engineering loop with optional session context.
    
    Args:
        requirement: The design requirement
        max_iterations: Maximum optimization iterations
        session_context: Optional conversation history for context
        
    Returns:
        Dictionary with design and validation results
    """
    # Prepend session context to requirement if provided
    effective_requirement = requirement
    if session_context:
        effective_requirement = f"Previous conversation context:\n{session_context}\n\nCurrent requirement: {requirement}"
    
    # Rest of existing logic remains largely the same
    # ... existing implementation ...
```

### Component 4: Visualizer Integration Preparation

Prepare the visualizer to accept DesignProject data (would be implemented in the visualizer directory):

```javascript
// Conceptual changes needed in visualizer/src/App.jsx or similar
// This shows the interface the visualizer would need to accept

function App() {
  const [designData, setDesignData] = useState(null);
  const [validationResults, setValidationResults] = useState(null);
  
  // In real implementation, this would extract design data from URL params or props
  // For CLI integration, we'd pass data via a temporary file or URL parameter
  
  useEffect(() => {
    // Extract design data from URL or props
    const urlParams = new URLSearchParams(window.location.search);
    const designJson = urlParams.get('design');
    
    if (designJson) {
      try {
        const design = JSON.parse(decodeURIComponent(designJson));
        setDesignData(design);
      } catch (e) {
        console.error('Failed to parse design data:', e);
      }
    }
    
    // Similarly for validation results
    const validationJson = urlParams.get('validation');
    if (validationJson) {
      try {
        const validation = JSON.parse(decodeURIComponent(validationJson));
        setValidationResults(validation);
      } catch (e) {
        console.error('Failed to parse validation data:', e);
      }
    }
  }, []);
  
  // Render function would use designData and validationResults
  // to display the schematic and overlay validation feedback
}
```

## Implementation Plan

### Week 1: Foundation
1. Create session management module (`src/ai/session.py`)
2. Write unit tests for session management
3. Modify orchestrator to accept session context (minimal change)
4. Test basic session creation and history tracking

### Week 2: CLI Integration
1. Implement `agent-run` command with session support
2. Implement `session-list` and `session-show` commands
3. Add basic visualization preparation (stub for now)
4. Test end-to-end flow: create session → run design → view session

### Week 3: Visualization Integration
1. Prepare visualizer to accept DesignProject data via URL/props
2. Implement `visualize` command that prepares data for visualizer
3. Create integration tests for CLI-visualizer data flow
4. Test visualization preparation with sample designs

### Week 4: Polish & Documentation
1. Add comprehensive error handling and validation
2. Improve CLI help text and examples
3. Write user documentation for session management
4. Create example workflows demonstrating the feature
5. Run full test suite to ensure no regressions

## Success Criteria

### Functional Requirements
1. Users can create design sessions via CLI
2. Users can run AI-assisted design iterations within a session
3. Session history is preserved and accessible
4. Users can list and view session details
5. Users can visualize designs from sessions or files
6. Visualization preparation works correctly (even if full visualizer launch is stubbed)

### Non-Functional Requirements
1. All new code follows existing code style and conventions
2. Comprehensive unit tests cover new functionality (≥80% coverage)
3. No regressions in existing functionality
4. Clear error messages and helpful CLI feedback
5. Documentation matches implementation

### Metrics for Success
1. Command completion time: <2 seconds for basic operations
2. Memory usage: Sessions should not leak memory
3. Test coverage: New features ≥80% line coverage
4. User feedback: Positive responses to iterative design capability
5. Adoption potential: Clear path to enhanced features in later phases

## Risks and Mitigation

### Risk 1: Scope Creep
**Mitigation**: Strictly define MVP as session management + CLI visualization preparation. Defer advanced features (real-time collaboration, advanced visualization) to later phases.

### Risk 2: Visualizer Integration Complexity
**Mitigation**: Focus on data preparation contract first. The actual visualizer launch can be stubbed initially with clear indication of where it would happen.

### Risk 3: Session State Management Overhead
**Mitigation**: Implement sessions as in-memory storage initially. Add persistence (file-based) only if needed for the MVP.

### Risk 4: Breaking Changes to Existing Orchestrator
**Mitigation**: Make session context optional. Existing code paths remain unchanged. Add new method overloads rather than modifying existing signatures.

## Dependencies

### Internal Dependencies
- Existing AI orchestrator (`src/ai/orchestrator.py`)
- Existing validation engine (`src/validation/engine.py`)
- Existing component registry (`src/components/registry.py`)
- Existing visualizer directory (for integration preparation)

### External Dependencies
- None beyond existing requirements (Typer, Rich, Pydantic, etc.)

## Estimated Effort

- **Session Management**: 2-3 days
- **CLI Commands**: 3-4 days  
- **Orchestrator Enhancement**: 1-2 days
- **Visualizer Preparation**: 2-3 days
- **Testing & Documentation**: 2-3 days
- **Total**: 10-15 days (2-3 weeks)

## Connection to Target Architecture

This task implements foundational elements from the target architecture:
1. **Application/Orchestration Layer**: Design Session Management component
2. **Presentation Layer**: CLI tool enhancements and visualization preparation
3. **Domain/Services Layer**: Builds on existing validation and AI capabilities
4. **Infrastructure Layer**: Uses existing component registry and preparation for visualizer data flow

By completing this task, the Illustration Engine gains:
- Iterative design capability (critical for complex designs)
- Visual feedback pathway (addresses major usability gap)
- Session context for improved AI understanding
- Foundation for web interface and collaboration features

This delivers immediate value to users while clearly demonstrating progress toward the vision of a smart GenAI electronics illustrator.