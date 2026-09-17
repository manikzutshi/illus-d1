import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text } from '@react-three/drei';
import type { SceneGraph, SceneNode } from '../core/types';

interface Scene3DProps {
    sceneGraph: SceneGraph;
    onSelect: (id: string | null) => void;
    selected: string | null;
}

const NodeVisual: React.FC<{ node: SceneNode; selected: boolean; onSelect: () => void }> = ({ node, selected, onSelect }) => {
    const color = selected ? 'orange' : '#2c3e50';
    let geometry;
    let meshRot: [number, number, number] = [0, 0, 0];

    // Use placeholder geometry based on visual_type
    if (node.visual_type === 'board') {
        geometry = <boxGeometry args={[10, 1, 14]} />;
    } else if (node.visual_type === 'sensor') {
        geometry = <boxGeometry args={[8, 3, 4]} />;
    } else if (node.visual_type === 'led') {
        geometry = <cylinderGeometry args={[0.5, 0.5, 2]} />;
    } else if (node.visual_type === 'resistor') {
        geometry = <cylinderGeometry args={[0.2, 0.2, 3]} />;
        meshRot = [0, 0, Math.PI / 2];
    } else if (node.visual_type === 'power') {
        geometry = <boxGeometry args={[2, 2, 2]} />;
    } else {
        geometry = <boxGeometry args={[2, 2, 2]} />;
    }

    return (
        <group position={node.transform.position} rotation={node.transform.rotation}>
            <mesh rotation={meshRot} onClick={(e) => { e.stopPropagation(); onSelect(); }}>
                {geometry}
                <meshStandardMaterial color={color} />
            </mesh>
            <Text position={[0, 2, 0]} fontSize={1} color="black">
                {node.instance_id}
            </Text>
        </group>
    );
};

export const Scene3D: React.FC<Scene3DProps> = ({ sceneGraph, onSelect, selected }) => {
    return (
        <Canvas camera={{ position: [0, 20, 20], fov: 50 }} onPointerMissed={() => onSelect(null)}>
            <ambientLight intensity={0.5} />
            <directionalLight position={[10, 10, 5]} intensity={1} />
            <OrbitControls makeDefault />

            {/* Breadboard Base (placeholder) */}
            <mesh position={[0, -1, 0]}>
                <boxGeometry args={[30, 0.5, 20]} />
                <meshStandardMaterial color="#f0f0f0" />
            </mesh>
            <gridHelper args={[30, 30]} position={[0, -0.74, 0]} />

            {/* Nodes */}
            {sceneGraph.nodes.map(node => (
                <NodeVisual 
                    key={node.instance_id} 
                    node={node} 
                    selected={selected === node.instance_id}
                    onSelect={() => onSelect(node.instance_id)} 
                />
            ))}

            {/* Wires */}
            {sceneGraph.wires.map(wire => (
                <group key={wire.net_id}>
                    {/* Render polyline segments */}
                    {wire.path.map((p, i) => {
                        if (i === wire.path.length - 1) return null;
                        const next = wire.path[i + 1];
                        return (
                            <line key={i}>
                                <bufferGeometry attach="geometry">
                                    <bufferAttribute args={[new Float32Array([...p, ...next]), 3]}
                                        attach="attributes-position"
                                        
                                        
                                        
                                    />
                                </bufferGeometry>
                                <lineBasicMaterial attach="material" color={wire.color} linewidth={2} />
                            </line>
                        );
                    })}
                </group>
            ))}
        </Canvas>
    );
};
