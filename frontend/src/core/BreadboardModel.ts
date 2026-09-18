import type { Vector3 } from './types';

export class BreadboardModel {
    public pitch = 1.0; // 1 unit = 2.54mm in physical space
    public cols = 30;
    
    // Y is up in 3D, so breadboard is on X-Z plane
    // Let's place origin (0,0,0) at the center of the breadboard
    
    // Top Power Rail (red/blue)
    // Terminal rows A-E
    // Trench
    // Terminal rows F-J
    // Bottom Power Rail (red/blue)

    // X represents columns (1 to 30) -> left to right
    // Z represents rows (power top, A-E, F-J, power bottom) -> top to bottom
    
    // Z offsets (in pitches) from center:
    // trench is at Z=0
    // E is Z = -0.5, A is Z = -4.5
    // F is Z = 0.5, J is Z = 4.5
    // Top power rails (GND, VCC) at Z = -6.5, Z = -7.5
    // Bottom power rails (GND, VCC) at Z = 6.5, Z = 7.5

    // X offsets:
    // col 1 to 30 => center is 15.5
    // col 1 is X = -14.5
    // col 30 is X = 14.5

    public colToX(col: number): number {
        // col: 1 to 30
        return (col - 15.5) * this.pitch;
    }

    public rowToZ(row: string): number {
        const rowOffsets: Record<string, number> = {
            'A': -4.5, 'B': -3.5, 'C': -2.5, 'D': -1.5, 'E': -0.5,
            'F': 0.5, 'G': 1.5, 'H': 2.5, 'I': 3.5, 'J': 4.5
        };
        return (rowOffsets[row.toUpperCase()] || 0) * this.pitch;
    }

    public holeToWorld(col: number, row: string): Vector3 {
        return [this.colToX(col), 0, this.rowToZ(row)];
    }

    // Top power rails (we'll call them 'top-vcc', 'top-gnd')
    // col block 1-25 typical, let's just map them by col roughly
    public powerHoleToWorld(side: 'top' | 'bottom', type: 'vcc' | 'gnd', col: number): Vector3 {
        const x = this.colToX(col);
        let z = 0;
        if (side === 'top') {
            z = type === 'gnd' ? -7.5 : -6.5; // GND usually outermost
        } else {
            z = type === 'gnd' ? 7.5 : 6.5; // GND usually outermost
        }
        return [x, 0, z];
    }

    public isValidHole(col: number, row: string): boolean {
        if (col < 1 || col > this.cols) return false;
        return /^[A-J]$/i.test(row);
    }
}
