import React, { useMemo } from 'react';
import * as THREE from 'three';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text, Bounds, useGLTF } from '@react-three/drei';
import type { SceneGraph, SceneNode } from '../core/types';

interface Scene3DProps {
    sceneGraph: SceneGraph;
    onSelect: (id: string | null) => void;
    selected: string | null;
    camView?: string;
    showLabels?: boolean;
    showAnchors?: boolean;
}

const GLBModel: React.FC<{ url: string }> = ({ url }) => {
    const { scene } = useGLTF(url);
    const cloned = useMemo(() => scene.clone(), [scene]);
    return <primitive object={cloned} />;
};

const NodeVisual: React.FC<{ node: SceneNode; selected: boolean; onSelect: () => void; showLabels: boolean; showAnchors: boolean }> = ({ node, selected, onSelect, showLabels, showAnchors }) => {
    const color = selected ? 'orange' : '#2c3e50';
    
    // Default fallback
    let geometry = (
        <>
            <boxGeometry args={[2, 2, 2]} />
            <meshStandardMaterial color={color} />
        </>
    );

    if (node.asset_source === 'glb' && node.asset_url) {
        geometry = <GLBModel url={node.asset_url} />;
    } else if (node.visual_type === 'board' || node.visual_type === 'esp32') {
        // ESP32 Representation
        geometry = (
            <group>
                {/* PCB Base */}
                <mesh position={[0, -0.2, 0]}>
                    <boxGeometry args={[14, 0.2, 10.5]} />
                    <meshStandardMaterial color={selected ? 'orange' : '#222'} />
                </mesh>
                {/* Headers */}
                <mesh position={[0, -0.1, -4.5]}>
                    <boxGeometry args={[13, 0.2, 0.5]} />
                    <meshStandardMaterial color="black" />
                </mesh>
                <mesh position={[0, -0.1, 4.5]}>
                    <boxGeometry args={[13, 0.2, 0.5]} />
                    <meshStandardMaterial color="black" />
                </mesh>
                {/* USB */}
                <mesh position={[-6.5, 0.2, 0]}>
                    <boxGeometry args={[1.5, 0.4, 3]} />
                    <meshStandardMaterial color="silver" />
                </mesh>
                {/* Shield */}
                <mesh position={[0, 0.1, 0]}>
                    <boxGeometry args={[5, 0.3, 4]} />
                    <meshStandardMaterial color="#444" />
                </mesh>
            </group>
        );
    } else if (node.visual_type === 'sensor' || node.visual_type === 'hcsr04') {
        geometry = (
            <group>
                {/* PCB */}
                <mesh position={[0, -0.1, 0]}>
                    <boxGeometry args={[4.5, 0.2, 2.5]} />
                    <meshStandardMaterial color={selected ? 'orange' : '#225588'} />
                </mesh>
                {/* Transducers */}
                <mesh position={[-1.2, 0.5, 0]} rotation={[Math.PI/2, 0, 0]}>
                    <cylinderGeometry args={[0.8, 0.8, 1]} />
                    <meshStandardMaterial color="silver" />
                </mesh>
                <mesh position={[1.2, 0.5, 0]} rotation={[Math.PI/2, 0, 0]}>
                    <cylinderGeometry args={[0.8, 0.8, 1]} />
                    <meshStandardMaterial color="silver" />
                </mesh>
                {/* Header */}
                <mesh position={[0, -0.1, 1.1]}>
                    <boxGeometry args={[2, 0.2, 0.5]} />
                    <meshStandardMaterial color="black" />
                </mesh>
            </group>
        );
    } else if (node.visual_type === 'led') {
        geometry = (
            <group>
                <mesh position={[0, 1, 0]}>
                    <cylinderGeometry args={[0.25, 0.25, 0.5]} />
                    <meshStandardMaterial color={selected ? 'orange' : 'red'} transparent opacity={0.8} />
                </mesh>
                <mesh position={[0, 1.25, 0]}>
                    <sphereGeometry args={[0.25, 16, 16]} />
                    <meshStandardMaterial color={selected ? 'orange' : 'red'} transparent opacity={0.8} />
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
            
            {showLabels && (
                <Text position={[0, 2.5, 0]} fontSize={0.6} color="black" outlineWidth={0.05} outlineColor="white">
                    {node.instance_id}
                </Text>
            )}

            {showAnchors && Object.entries(node.anchors).map(([pin_id, localPos]) => (
                <mesh key={pin_id} position={localPos}>
                    <sphereGeometry args={[0.15]} />
                    <meshBasicMaterial color="magenta" />
                    <Text position={[0, 0.3, 0]} fontSize={0.3} color="magenta">{pin_id}</Text>
                </mesh>
            ))}
        </group>
    );
};

const WireTube: React.FC<{ path: THREE.Vector3[]; color: string }> = ({ path, color }) => {
    // Generate a smoothed curve from the Manhattan points
    const curve = useMemo(() => {
        if (path.length < 2) return null;
        // Use CatmullRomCurve3 for smoothed tube
        return new THREE.CatmullRomCurve3(path, false, 'catmullrom', 0.1);
    }, [path]);

    if (!curve) return null;

    return (
        <mesh>
            <tubeGeometry args={[curve, 64, 0.08, 8, false]} />
            <meshStandardMaterial color={color} />
        </mesh>
    );
};

export const Scene3D: React.FC<Scene3DProps> = ({ sceneGraph, onSelect, selected, camView = 'iso', showLabels = true, showAnchors = false }) => {
    
    let camPos: [number, number, number] = [0, 25, 25];
    if (camView === 'top') camPos = [0, 40, 0];
    else if (camView === 'front') camPos = [0, 8, 30];

    return (
        <Canvas key={camView} camera={{ position: camPos, fov: 45 }} onPointerMissed={() => onSelect(null)}>
            <ambientLight intensity={0.6} />
            <directionalLight position={[10, 15, 10]} intensity={1.5} castShadow />
            <OrbitControls makeDefault />

            <Bounds fit clip observe margin={1.2}>
                {/* Breadboard Base (from GLB) */}
                <group position={[0, -0.4, 0]}>
                    <GLBModel url="/models/breadboard.glb" />
                </group>

                {/* Nodes */}
                {sceneGraph.nodes.map(node => (
                    <NodeVisual 
                        key={node.instance_id} 
                        node={node} 
                        selected={selected === node.instance_id}
                        onSelect={() => onSelect(node.instance_id)} 
                        showLabels={showLabels}
                        showAnchors={showAnchors}
                    />
                ))}

                {/* Wires */}
                {sceneGraph.wires.map(wire => (
                    <WireTube 
                        key={wire.net_id} 
                        path={wire.path.map(p => new THREE.Vector3(...p))} 
                        color={wire.color} 
                    />
                ))}
            </Bounds>
        </Canvas>
    );
};
