import { describe, it, expect } from 'vitest';
import { SceneBuilder } from './SceneBuilder';
import type { DesignProject } from './types';

const fixture: DesignProject = {
    project_id: "test",
    name: "Test",
    components: [
        { instance_id: "u1", component_type: "board:esp32-devkit-v1" },
        { instance_id: "s1", component_type: "sensor:hc-sr04" },
        { instance_id: "unknown1", component_type: "fake:part" }
    ],
    nets: [
        { net_id: "n1", connections: [{ instance_id: "u1", pin_id: "VIN" }, { instance_id: "s1", pin_id: "VCC" }] }
    ]
};

describe('SceneBuilder', () => {
    it('should build a scene graph deterministically', () => {
        const builder = new SceneBuilder();
        const graph = builder.build(fixture);
        
        // 1. Every component has a visual definition
        expect(graph.nodes.length).toBe(3);
        
        // 2. Unknown component types produce a visible 'unsupported visual' state rather than crashing
        const unknownNode = graph.nodes.find(n => n.instance_id === 'unknown1');
        expect(unknownNode).toBeDefined();
        expect(unknownNode?.visual_type).toBe('unknown');
        
        // 3. Every net resolves to valid visual endpoints
        expect(graph.wires.length).toBe(1);
        expect(graph.wires[0].path.length).toBe(5);
        
        // 4. Same DesignProject produces same layout
        const graph2 = builder.build(fixture);
        expect(graph).toEqual(graph2);
    });
});
