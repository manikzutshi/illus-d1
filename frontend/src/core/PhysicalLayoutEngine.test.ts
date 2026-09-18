import { describe, it, expect } from 'vitest';
import { PhysicalLayoutEngine } from './PhysicalLayoutEngine';
import { SceneBuilder } from './SceneBuilder';
import type { DesignProject } from './types';

const fixture: DesignProject = {
    project_id: "test",
    name: "Test",
    components: [
        { instance_id: "u1", component_type: "board:esp32-devkit-v1" },
        { instance_id: "s1", component_type: "sensor:hc-sr04" },
        { instance_id: "r1", component_type: "passive:resistor-tht", parameters: { resistance: "1k" } },
        { instance_id: "r2", component_type: "passive:resistor-tht", parameters: { resistance: "2k" } },
        { instance_id: "d1", component_type: "passive:led-5mm" }
    ],
    nets: [
        { net_id: "n1", connections: [{ instance_id: "u1", pin_id: "VIN" }, { instance_id: "s1", pin_id: "VCC" }] },
        { net_id: "n2", connections: [{ instance_id: "s1", pin_id: "ECHO" }, { instance_id: "r1", pin_id: "PIN1" }] }
    ]
};

describe('PhysicalLayoutEngine', () => {
    it('should place components deterministically', () => {
        const engine = new PhysicalLayoutEngine();
        const layout1 = engine.computeLayout(fixture);
        const layout2 = engine.computeLayout(fixture);
        
        expect(layout1.nodes['u1'].position).toEqual(layout2.nodes['u1'].position);
        expect(layout1.nodes['s1'].position).toEqual(layout2.nodes['s1'].position);
    });

    it('should generate world anchors derived from breadboard holes', () => {
        const engine = new PhysicalLayoutEngine();
        const layout = engine.computeLayout(fixture);
        
        const r1 = layout.nodes['r1'];
        expect(r1).toBeDefined();
        // Z values for row A (-4.5 pitches) and row D (-1.5 pitches)
        // Our pitch is 1.0. Row A Z = -4.5. Row D Z = -1.5. 
        expect(r1.world_anchors['PIN1'][2]).toBe(-4.5);
        expect(r1.world_anchors['PIN2'][2]).toBe(-1.5);
    });
});

describe('SceneBuilder with Physical Layout', () => {
    it('should resolve wires to actual instance pin anchors', () => {
        const builder = new SceneBuilder();
        const graph = builder.build(fixture);
        
        const wire = graph.wires.find(w => w.net_id === 'n2');
        expect(wire).toBeDefined();
        
        const r1Node = graph.nodes.find(n => n.instance_id === 'r1');
        const s1Node = graph.nodes.find(n => n.instance_id === 's1');
        
        // Ensure path starts and ends exactly at the world anchors with slight elevation
        // wire.path[0] is s1's ECHO world anchor.
        const startX = wire!.path[0][0];
        const startZ = wire!.path[0][2];
        expect(startX).toBe(s1Node!.world_anchors['ECHO'][0]);
        expect(startZ).toBe(s1Node!.world_anchors['ECHO'][2]);
        
        const endX = wire!.path[wire!.path.length - 1][0];
        const endZ = wire!.path[wire!.path.length - 1][2];
        expect(endX).toBe(r1Node!.world_anchors['PIN1'][0]);
        expect(endZ).toBe(r1Node!.world_anchors['PIN1'][2]);
    });
});
