import { getAssetDefinition } from './assets';
import type { DesignProject, SceneGraph, SceneNode, SceneWire, Vector3 } from './types';

// Visual definitions dictating primitive size and pin anchors

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
            const def = getAssetDefinition(comp.component_type);

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
            
            let color = '#00aa00'; // Default signal green
            if (net.net_type === 'power') {
                color = '#ff0000';
            } else if (net.net_type === 'ground') {
                color = '#000000';
            } else {
                // Heuristic based on pin names
                const isGnd = net.connections.some(c => c.pin_id.toUpperCase().includes('GND'));
                const isPower = net.connections.some(c => ['VCC', 'VIN', '3V3', '5V'].includes(c.pin_id.toUpperCase()));
                if (isPower) color = '#ff0000';
                else if (isGnd) color = '#000000';
                else color = '#e6c300'; // Yellow for standard signal
            }

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
