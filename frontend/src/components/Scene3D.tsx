import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text } from '@react-three/drei';
import type { SceneGraph, SceneNode } from '../core/types';

interface Scene3DProps {
    sceneGraph: SceneGraph;
    onSelect: (id: string | null) => void;
    selected: string | null;
    camView?: string;
}

const NodeVisual: React.FC<{ node: SceneNode; selected: boolean; onSelect: () => void }> = ({ node, selected, onSelect }) => {
    const color = selected ? 'orange' : '#2c3e50';
    
    
    // Default fallback
    let geometry = (
        <>
            <boxGeometry args={[2, 2, 2]} />
            <meshStandardMaterial color={color} />
        </>
    );

    if (node.visual_type === 'board') {
        geometry = (
            <group>
                <mesh position={[0, -0.2, 0]}>
                    <boxGeometry args={[13.5, 0.2, 10.5]} />
                    <meshStandardMaterial color={selected ? 'orange' : '#111'} />
                </mesh>
                <mesh position={[-6, 0.2, 0]}>
                    <boxGeometry args={[1, 0.3, 3]} />
                    <meshStandardMaterial color="silver" />
                </mesh>
                <mesh position={[0, 0.1, 0]}>
                    <boxGeometry args={[5, 0.2, 4]} />
                    <meshStandardMaterial color="#333" />
                </mesh>
            </group>
        );
    } else if (node.visual_type === 'sensor') {
        geometry = (
            <group>
                <mesh position={[0, -0.1, 0]}>
                    <boxGeometry args={[4, 0.2, 2]} />
                    <meshStandardMaterial color={selected ? 'orange' : '#225588'} />
                </mesh>
                <mesh position={[-1, 0.5, 0]} rotation={[Math.PI/2, 0, 0]}>
                    <cylinderGeometry args={[0.7, 0.7, 1]} />
                    <meshStandardMaterial color="silver" />
                </mesh>
                <mesh position={[1, 0.5, 0]} rotation={[Math.PI/2, 0, 0]}>
                    <cylinderGeometry args={[0.7, 0.7, 1]} />
                    <meshStandardMaterial color="silver" />
                </mesh>
            </group>
        );
    } else if (node.visual_type === 'led') {
        geometry = (
            <group>
                <mesh position={[0, 1, 0]}>
                    <cylinderGeometry args={[0.25, 0.25, 0.5]} />
                    <meshStandardMaterial color={selected ? 'orange' : 'red'} />
                </mesh>
                <mesh position={[0, 1.25, 0]}>
                    <sphereGeometry args={[0.25, 16, 16]} />
                    <meshStandardMaterial color={selected ? 'orange' : 'red'} />
                </mesh>
            </group>
        );
    } else if (node.visual_type === 'resistor') {
        geometry = (
            <group>
                <mesh position={[0, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                    <cylinderGeometry args={[0.15, 0.15, 1.5]} />
                    <meshStandardMaterial color={selected ? 'orange' : '#e6cca3'} />
                </mesh>
                <mesh position={[-0.5, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                    <cylinderGeometry args={[0.16, 0.16, 0.2]} />
                    <meshStandardMaterial color="red" />
                </mesh>
                <mesh position={[0, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                    <cylinderGeometry args={[0.16, 0.16, 0.2]} />
                    <meshStandardMaterial color="black" />
                </mesh>
                <mesh position={[0.5, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                    <cylinderGeometry args={[0.16, 0.16, 0.2]} />
                    <meshStandardMaterial color="brown" />
                </mesh>
            </group>
        );
    }

    return (
        <group position={node.transform.position} rotation={node.transform.rotation}>
            <group onClick={(e) => { e.stopPropagation(); onSelect(); }}>
                {geometry}
            </group>
            <Text position={[0, 2, 0]} fontSize={0.6} color="black" outlineWidth={0.05} outlineColor="white">
                {node.instance_id}
            </Text>
        </group>
    );
}

export const Scene3D: React.FC<Scene3DProps> = ({ sceneGraph, onSelect, selected, camView = 'iso' }) => {
    let camPos: [number, number, number] = [0, 20, 20];
    if (camView === 'top') camPos = [0, 30, 0];
    else if (camView === 'front') camPos = [0, 5, 30];

    return (
        <Canvas key={camView} camera={{ position: camPos, fov: 50 }} onPointerMissed={() => onSelect(null)}>
            <ambientLight intensity={0.5} />
            <directionalLight position={[10, 10, 5]} intensity={1} />
            <OrbitControls makeDefault />

            {/* Breadboard Base */}
            <group position={[0, -0.25, 0]}>
                {/* Main Body */}
                <mesh position={[0, 0, 0]}>
                    <boxGeometry args={[32, 0.5, 17]} />
                    <meshStandardMaterial color="#ffffff" />
                </mesh>
                
                {/* Center Trench */}
                <mesh position={[0, 0.25, 0]}>
                    <boxGeometry args={[30, 0.1, 1]} />
                    <meshStandardMaterial color="#333333" />
                </mesh>

                {/* Power lines (red/blue) */}
                <mesh position={[0, 0.25, -6.5]}><boxGeometry args={[30, 0.05, 0.1]} /><meshStandardMaterial color="blue" /></mesh>
                <mesh position={[0, 0.25, -7.5]}><boxGeometry args={[30, 0.05, 0.1]} /><meshStandardMaterial color="red" /></mesh>
                
                <mesh position={[0, 0.25, 6.5]}><boxGeometry args={[30, 0.05, 0.1]} /><meshStandardMaterial color="blue" /></mesh>
                <mesh position={[0, 0.25, 7.5]}><boxGeometry args={[30, 0.05, 0.1]} /><meshStandardMaterial color="red" /></mesh>

                {/* Grid indicator (approximate holes) */}
                <gridHelper args={[30, 30, '#ddd', '#ddd']} position={[0, 0.26, 0]} />
            </group>

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
