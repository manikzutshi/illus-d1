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

import { PhysicalLayoutEngine } from './PhysicalLayoutEngine';

export class SceneBuilder {
    private layoutEngine = new PhysicalLayoutEngine();
    

    build(project: DesignProject): SceneGraph {
        const nodes: SceneNode[] = [];
        const wires: SceneWire[] = [];

        // 1. Compute Physical Layout
        const layout = this.layoutEngine.computeLayout(project);

        // 2. Build Nodes
        project.components.forEach((comp) => {
            const def = VISUAL_DEFINITIONS[comp.component_type] || {
                visual_type: 'unknown',
                width: 2, height: 2, depth: 2,
                anchors: {}
            };

            const phys = layout.nodes[comp.instance_id];
            
            // Map world anchors back to local for the 3D mesh if needed, 
            // but we'll supply world_anchors so 3D can just use them.
            const localAnchors: Record<string, Vector3> = {};
            for (const [p, w] of Object.entries(phys.world_anchors)) {
                localAnchors[p] = [
                    w[0] - phys.position[0],
                    w[1] - phys.position[1],
                    w[2] - phys.position[2]
                ];
            }

            nodes.push({
                instance_id: comp.instance_id,
                component_type: comp.component_type,
                visual_type: def.visual_type,
                transform: { position: phys.position, rotation: phys.rotation },
                anchors: localAnchors,
                world_anchors: phys.world_anchors,
                parameters: comp.parameters || {}
            });
        });

        // 3. Build Wires with Manhattan Routing
        let wireHeightOffset = 0.2; // to avoid z-fighting between wires
        project.nets.forEach(net => {
            if (net.connections.length < 2) return;
            
            const color = net.net_type === 'power' ? '#ff0000' : 
                          net.net_type === 'ground' ? '#000000' : '#00aa00';

            // Just route point to point sequentially with intermediate waypoints
            const path: Vector3[] = [];
            
            for (let i = 0; i < net.connections.length; i++) {
                const conn = net.connections[i];
                const node = layout.nodes[conn.instance_id];
                if (!node) continue;
                
                // Fallback to component center if pin anchor is missing
                const startPos = node.world_anchors[conn.pin_id] || [node.position[0], 0.2, node.position[2]];
                
                if (i === 0) {
                    path.push(startPos);
                    path.push([startPos[0], startPos[1] + 1.5 + wireHeightOffset, startPos[2]]);
                } else {
                    const prevConn = net.connections[i-1];
                    const prevNode = layout.nodes[prevConn.instance_id];
                    const prevPos = prevNode?.world_anchors[prevConn.pin_id] || [0,0,0];
                    
                    // Manhattan routing
                    const h = 1.5 + wireHeightOffset;
                    path.push([startPos[0], h, prevPos[2]]);
                    path.push([startPos[0], h, startPos[2]]);
                    path.push(startPos);
                }
            }
            wireHeightOffset += 0.2;

            wires.push({
                net_id: net.net_id,
                path,
                color
            });
        });

        return { nodes, wires };
    }
}
