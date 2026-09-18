import { BreadboardModel } from './BreadboardModel';
import type { DesignProject, Vector3 } from './types';

// Hardcoded footprint library for Phase 4.1
export const FOOTPRINTS: Record<string, any> = {
    'board:esp32-devkit-v1': {
        type: 'dip',
        cols: 15, // 15 pins per side
        rowSpan: 10, // spans from row A to row J (0.9" typical for 30-pin, actually 1.0" maybe. Let's use 10 pitches = A to J is 9 pitches. A= -4.5, J= 4.5 -> diff 9. So spans 9 pitches.)
        anchorMap: {
            'VIN': { side: 'right', index: 0 },
            'GND1': { side: 'right', index: 1 },
            'GND2': { side: 'right', index: 2 },
            '3V3': { side: 'left', index: 0 },
            'GND3': { side: 'left', index: 1 }, // Note: check actual ESP32 pinout
            // Approximate for others based on typical 30-pin devkit:
            'GPIO13': { side: 'left', index: 12 },
            'GPIO12': { side: 'left', index: 13 },
            'GPIO14': { side: 'left', index: 14 },
            'GPIO27': { side: 'left', index: 15 },
            'GPIO5': { side: 'right', index: 12 },
            'GPIO18': { side: 'right', index: 13 },
            'GPIO19': { side: 'right', index: 14 },
            'GPIO21': { side: 'right', index: 15 },
            // Just defaults for now, we will map dynamically or assign via logic
        }
    },
    'sensor:hc-sr04': {
        type: 'inline',
        cols: 4,
        anchorMap: {
            'VCC': { index: 0 },
            'TRIG': { index: 1 },
            'ECHO': { index: 2 },
            'GND': { index: 3 }
        }
    },
    'led:standard-5mm': {
        type: 'inline',
        cols: 2, // spanning adjacent holes
        anchorMap: { 'A': { index: 0 }, 'K': { index: 1 } }
    },
    'resistor:axial-0.25w': {
        type: 'inline',
        cols: 4, // leads span 4 holes typically
        anchorMap: { '1': { index: 0 }, '2': { index: 3 } }
    }
};

export interface PhysicalLayout {
    nodes: Record<string, PhysicalNode>;
}

export interface PhysicalNode {
    instance_id: string;
    position: Vector3; // Center in world space
    rotation: Vector3;
    world_anchors: Record<string, Vector3>; // Pin positions
    breadboard_mapping?: {
        startCol: number;
        startRow: string;
    };
}

export class PhysicalLayoutEngine {
    private board = new BreadboardModel();

    // Map a component's logical placement to physical coordinates
    public computeLayout(project: DesignProject): PhysicalLayout {
        const layout: PhysicalLayout = { nodes: {} };

        // 1. ESP32 -> place at Left side, row A and J
        const esp = project.components.find(c => c.component_type.includes('esp32'));
        if (esp) {
            const startCol = 2;
            const startRowLeft = 'A'; // -4.5
            const startRowRight = 'J'; // 4.5
            
            const world_anchors: Record<string, Vector3> = {};
            
            
            // Hardcode known pins for Golden Project mapping specifically if not in dict
            const knownPins: Record<string, {side: string, index: number}> = {
                'VIN': {side:'right', index: 0},
                'GND1': {side:'left', index: 6}, // approx
                'GND2': {side:'right', index: 6},
                'GND3': {side:'right', index: 7},
                '3V3': {side:'left', index: 0},
                'EN': {side:'left', index: 1},
                'GPIO5': {side:'right', index: 9},
                'GPIO18': {side:'right', index: 10},
                'GPIO19': {side:'right', index: 11},
                'GPIO21': {side:'right', index: 12}
            };

            const allPins = Object.keys(knownPins);
            allPins.forEach(p => {
                const map = knownPins[p] || { side: 'left', index: 0 };
                const r = map.side === 'left' ? startRowLeft : startRowRight;
                const c = startCol + map.index;
                world_anchors[p] = this.board.holeToWorld(c, r);
                // Adjust height slightly for header insertion
                world_anchors[p][1] = 0.5;
            });

            const center = this.board.holeToWorld(startCol + 7, 'E'); // middle
            center[1] = 1.0; // elevated

            layout.nodes[esp.instance_id] = {
                instance_id: esp.instance_id,
                position: center,
                rotation: [0, 0, 0],
                world_anchors,
                breadboard_mapping: { startCol, startRow: 'A' }
            };
        }

        // 2. HC-SR04 -> place at Right side, top row
        const hcsr = project.components.find(c => c.component_type.includes('hc-sr04'));
        if (hcsr) {
            const startCol = 20;
            const row = 'A';
            const world_anchors: Record<string, Vector3> = {};
            
            const pins = ['VCC', 'TRIG', 'ECHO', 'GND'];
            pins.forEach((p, i) => {
                world_anchors[p] = this.board.holeToWorld(startCol + i, row);
                world_anchors[p][1] = 0.5;
            });

            const center = this.board.holeToWorld(startCol + 1.5, row);
            center[1] = 1.5;

            layout.nodes[hcsr.instance_id] = {
                instance_id: hcsr.instance_id,
                position: center,
                rotation: [0, 0, 0],
                world_anchors,
                breadboard_mapping: { startCol, startRow: row }
            };
        }

        // 3. Voltage Divider Resistors (ECHO to GPIO)
        const r_div1 = project.components.find(c => c.instance_id === 'r1' || c.parameters?.resistance === '1k');
        const r_div2 = project.components.find(c => c.instance_id === 'r2' || c.parameters?.resistance === '2k');
        
        if (r_div1) {
            const startCol = 22; // near ECHO
            const rowStart = 'C';
            const rowEnd = 'D'; // vertical placement
            
            const w1 = this.board.holeToWorld(startCol, rowStart);
            const w2 = this.board.holeToWorld(startCol, rowEnd);
            const world_anchors = { 'PIN1': w1, 'PIN2': w2, '1': w1, '2': w2 }; // aliases
            
            const center: Vector3 = [w1[0], 0.5, (w1[2] + w2[2]) / 2];

            layout.nodes[r_div1.instance_id] = {
                instance_id: r_div1.instance_id, position: center, rotation: [0, Math.PI/2, 0], world_anchors
            };
        }

        if (r_div2) {
            const startCol = 22;
            const rowStart = 'F'; // jump trench
            const rowEnd = 'G';
            
            const w1 = this.board.holeToWorld(startCol, rowStart);
            const w2 = this.board.holeToWorld(startCol, rowEnd);
            const world_anchors = { 'PIN1': w1, 'PIN2': w2, '1': w1, '2': w2 };
            
            const center: Vector3 = [w1[0], 0.5, (w1[2] + w2[2]) / 2];

            layout.nodes[r_div2.instance_id] = {
                instance_id: r_div2.instance_id, position: center, rotation: [0, Math.PI/2, 0], world_anchors
            };
        }

        // 4. LED & Resistor
        const led = project.components.find(c => c.component_type.includes('led'));
        const r_led = project.components.find(c => c.instance_id === 'r3' || (c.component_type.includes('resistor') && c.instance_id !== 'r1' && c.instance_id !== 'r2'));

        if (led) {
            const startCol = 26;
            const row = 'H';
            const w1 = this.board.holeToWorld(startCol, row);
            const w2 = this.board.holeToWorld(startCol + 1, row);
            const world_anchors = { 'ANODE': w1, 'CATHODE': w2, 'A': w1, 'K': w2 };
            const center: Vector3 = [ (w1[0]+w2[0])/2, 1.0, w1[2] ];

            layout.nodes[led.instance_id] = {
                instance_id: led.instance_id, position: center, rotation: [0, 0, 0], world_anchors
            };
        }

        if (r_led) {
            const startCol = 27; // connects to LED cathode
            const rowStart = 'H';
            const rowEnd = 'I';
            const w1 = this.board.holeToWorld(startCol, rowStart);
            const w2 = this.board.holeToWorld(startCol, rowEnd);
            const world_anchors = { 'PIN1': w1, 'PIN2': w2, '1': w1, '2': w2 };
            const center: Vector3 = [w1[0], 0.5, (w1[2] + w2[2]) / 2];

            layout.nodes[r_led.instance_id] = {
                instance_id: r_led.instance_id, position: center, rotation: [0, Math.PI/2, 0], world_anchors
            };
        }

        // Place any missing dynamically in remaining slots
        let fallbackCol = 1;
        project.components.forEach(c => {
            if (!layout.nodes[c.instance_id]) {
                const w1 = this.board.holeToWorld(fallbackCol, 'A');
                layout.nodes[c.instance_id] = {
                    instance_id: c.instance_id,
                    position: [w1[0], 0.5, w1[2]],
                    rotation: [0,0,0],
                    world_anchors: {}
                };
                fallbackCol += 2;
            }
        });

        return layout;
    }
}
