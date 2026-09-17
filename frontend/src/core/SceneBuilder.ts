import type { DesignProject, SceneGraph, SceneNode, SceneWire, Vector3 } from './types';

// Visual definitions dictating primitive size and pin anchors
const VISUAL_DEFINITIONS: Record<string, any> = {
    'board:esp32-devkit-v1': {
        visual_type: 'board',
        width: 10,
        height: 1,
        depth: 14,
        anchors: {
            'VIN': [-4, 0.5, 6],
            '3V3': [-4, 0.5, 5],
            'GND1': [-4, 0.5, 4],
            'GND2': [-4, 0.5, 3],
            'GPIO18': [4, 0.5, -3],
            // Simplified fallback for other pins
        }
    },
    'sensor:hc-sr04': {
        visual_type: 'sensor',
        width: 8,
        height: 3,
        depth: 4,
        anchors: {
            'VCC': [-1.5, 0, 2],
            'TRIG': [-0.5, 0, 2],
            'ECHO': [0.5, 0, 2],
            'GND': [1.5, 0, 2]
        }
    },
    'led:standard-5mm': {
        visual_type: 'led',
        width: 1,
        height: 2,
        depth: 1,
        anchors: {
            'A': [0, -1, 0],
            'K': [0, -1, -1]
        }
    },
    'resistor:axial-0.25w': {
        visual_type: 'resistor',
        width: 3,
        height: 0.5,
        depth: 0.5,
        anchors: {
            '1': [-1.5, 0, 0],
            '2': [1.5, 0, 0]
        }
    },
    'power:generic-5v': {
        visual_type: 'power',
        width: 2,
        height: 2,
        depth: 2,
        anchors: {
            'VCC': [0, 1, 0],
            'GND': [0, -1, 0]
        }
    }
};

export class SceneBuilder {
    build(project: DesignProject): SceneGraph {
        const nodes: SceneNode[] = [];
        const wires: SceneWire[] = [];

        // Track global pin positions for routing
        const globalAnchors: Record<string, Record<string, Vector3>> = {};

        // 1. Build Nodes
        project.components.forEach((comp, index) => {
            const def = VISUAL_DEFINITIONS[comp.component_type] || {
                visual_type: 'unknown',
                width: 2, height: 2, depth: 2,
                anchors: {}
            };

            // Layout fallback
            const pos: Vector3 = comp.layout 
                ? [comp.layout.x, comp.layout.y, comp.layout.z] 
                : [index * 5, 0, 0];
            const rot: Vector3 = comp.layout 
                ? [0, comp.layout.rotation * Math.PI / 180, 0] 
                : [0, 0, 0];

            // Resolve global anchors
            const anchors: Record<string, Vector3> = def.anchors || {};
            globalAnchors[comp.instance_id] = {};
            
            for (const [pin_id, localPos] of Object.entries(anchors)) {
                // Simplified transform (assuming mostly translation for now)
                globalAnchors[comp.instance_id][pin_id] = [
                    pos[0] + (localPos[0] as number),
                    pos[1] + (localPos[1] as number),
                    pos[2] + (localPos[2] as number)
                ];
            }

            nodes.push({
                instance_id: comp.instance_id,
                component_type: comp.component_type,
                visual_type: def.visual_type,
                transform: { position: pos, rotation: rot },
                anchors,
                parameters: comp.parameters || {}
            });
        });

        // 2. Build Wires
        project.nets.forEach(net => {
            // A simple wire connects all pins in sequence
            if (net.connections.length < 2) return;
            
            const color = net.net_type === 'power' ? '#ff0000' : 
                          net.net_type === 'ground' ? '#000000' : '#00aa00';

            const path: Vector3[] = [];
            
            net.connections.forEach(conn => {
                const nodeAnchors = globalAnchors[conn.instance_id];
                if (nodeAnchors) {
                    const pos = nodeAnchors[conn.pin_id] || globalAnchors[conn.instance_id]['1'] || [0, 0, 0];
                    // Add a small lift so wires don't Z-fight with breadboard
                    path.push([pos[0], pos[1] + 1, pos[2]]);
                }
            });

            wires.push({
                net_id: net.net_id,
                path,
                color
            });
        });

        return { nodes, wires };
    }
}
