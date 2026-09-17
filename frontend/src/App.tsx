import React, { useState, useEffect } from 'react';
import type { SceneGraph, DesignProject } from './core/types';
import { SceneBuilder } from './core/SceneBuilder';
import { Scene3D } from './components/Scene3D';
import { Schematic2D } from './components/Schematic2D';

const App: React.FC = () => {
    const [project, setProject] = useState<DesignProject | null>(null);
    const [sceneGraph, setSceneGraph] = useState<SceneGraph | null>(null);
    const [selectedInstance, setSelectedInstance] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // Load the smart_parking_valid.json mapped to project.json via CLI
        fetch('/project.json')
            .then(res => {
                if (!res.ok) throw new Error("Could not load project");
                return res.json();
            })
            .then((data: DesignProject) => {
                setProject(data);
                const builder = new SceneBuilder();
                setSceneGraph(builder.build(data));
            })
            .catch(err => {
                setError(err.message);
                console.error(err);
            });
    }, []);

    const handleSelect = (instanceId: string | null) => {
        setSelectedInstance(instanceId);
    };

    if (error) {
        return <div style={{ color: 'red', padding: 20 }}>Error: {error}</div>;
    }

    if (!project || !sceneGraph) {
        return <div style={{ padding: 20 }}>Loading DesignProject...</div>;
    }

    const selectedComponent = project.components.find(c => c.instance_id === selectedInstance);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'sans-serif' }}>
            {/* Header */}
            <div style={{ padding: 10, backgroundColor: '#333', color: '#fff' }}>
                <h2 style={{ margin: 0 }}>Illustration Engine - {project.name}</h2>
            </div>

            {/* Main Content */}
            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
                
                {/* Sidebar */}
                <div style={{ width: 250, borderRight: '1px solid #ccc', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
                    <div style={{ padding: 10, fontWeight: 'bold', borderBottom: '1px solid #eee' }}>Components</div>
                    {project.components.map(comp => (
                        <div 
                            key={comp.instance_id}
                            onClick={() => handleSelect(comp.instance_id)}
                            style={{
                                padding: 10,
                                cursor: 'pointer',
                                backgroundColor: selectedInstance === comp.instance_id ? '#e0f0ff' : 'transparent',
                                borderBottom: '1px solid #eee'
                            }}
                        >
                            <strong>{comp.instance_id}</strong>
                            <div style={{ fontSize: '0.8em', color: '#666' }}>{comp.component_type}</div>
                        </div>
                    ))}
                </div>

                {/* 3D View */}
                <div style={{ flex: 1, position: 'relative' }}>
                    <Scene3D sceneGraph={sceneGraph} onSelect={handleSelect} selected={selectedInstance} />
                </div>
            </div>

            {/* Bottom Panel */}
            <div style={{ height: 250, borderTop: '1px solid #ccc', display: 'flex' }}>
                <div style={{ flex: 1, borderRight: '1px solid #ccc', position: 'relative' }}>
                    <div style={{ position: 'absolute', top: 5, left: 10, fontWeight: 'bold' }}>2D Schematic</div>
                    <Schematic2D sceneGraph={sceneGraph}  selected={selectedInstance} />
                </div>
                <div style={{ width: 300, padding: 10, overflowY: 'auto' }}>
                    <div style={{ fontWeight: 'bold', marginBottom: 10 }}>Selected Details</div>
                    {selectedComponent ? (
                        <div>
                            <div><strong>Instance:</strong> {selectedComponent.instance_id}</div>
                            <div><strong>Type:</strong> {selectedComponent.component_type}</div>
                            {selectedComponent.parameters && Object.keys(selectedComponent.parameters).length > 0 && (
                                <div style={{ marginTop: 10 }}>
                                    <strong>Parameters:</strong>
                                    <pre style={{ fontSize: '0.9em', backgroundColor: '#f5f5f5', padding: 5 }}>
                                        {JSON.stringify(selectedComponent.parameters, null, 2)}
                                    </pre>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div style={{ color: '#888' }}>Select a component to view details.</div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default App;
