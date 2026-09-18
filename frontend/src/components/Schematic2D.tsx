import React, { useRef, useEffect } from 'react';
import type { SceneGraph } from '../core/types';

interface Schematic2DProps {
    sceneGraph: SceneGraph;
    
    selected: string | null;
}

export const Schematic2D: React.FC<Schematic2DProps> = ({ sceneGraph, selected }) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Clear
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Setup transform
        ctx.save();
        // Move origin to center roughly, scale up
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.scale(10, 10); // scale 3D coordinates to 2D pixels

        // Draw Wires
        sceneGraph.wires.forEach(wire => {
            ctx.beginPath();
            ctx.strokeStyle = wire.color;
            ctx.lineWidth = 0.2;
            wire.path.forEach((p, i) => {
                const x = p[0];
                const y = p[2];
                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    const prev = wire.path[i - 1];
                    
                    const py = prev[2];
                    // Manhattan step in 2D (go horizontally then vertically)
                    ctx.lineTo(x, py);
                    ctx.lineTo(x, y);
                }
            });
            ctx.stroke();
        });

        // Draw Nodes
        sceneGraph.nodes.forEach(node => {
            const isSelected = selected === node.instance_id;
            const x = node.transform.position[0];
            const y = node.transform.position[2]; // Z becomes Y in 2D schematic

            ctx.fillStyle = isSelected ? '#ffcc00' : '#ffffff';
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 0.1;

            let w = 4, h = 4;
            if (node.visual_type === 'board') { w = 10; h = 14; }
            if (node.visual_type === 'sensor') { w = 8; h = 4; }
            if (node.visual_type === 'resistor') { w = 3; h = 1; }

            ctx.fillRect(x - w/2, y - h/2, w, h);
            ctx.strokeRect(x - w/2, y - h/2, w, h);

            // Draw label
            ctx.fillStyle = '#000';
            ctx.font = '0.5px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            
            let label = node.instance_id;
            if (node.parameters?.resistance) {
                label += ` (${node.parameters.resistance})`;
            } else if (node.component_type.includes('hc-sr04')) {
                label += ' (Ultrasonic)';
            }
            
            ctx.fillText(label, x, y);
            
            // Draw anchors (pins)
            ctx.fillStyle = 'red';
            for (const [, pos] of Object.entries(node.world_anchors || node.anchors)) {
                ctx.beginPath();
                ctx.arc(pos[0], pos[2], 0.2, 0, Math.PI * 2);
                ctx.fill();
            }
        });

        ctx.restore();
    }, [sceneGraph, selected]);

    return (
        <div style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
            <canvas 
                ref={canvasRef} 
                width={800} 
                height={400} 
                style={{ width: '100%', height: '100%', objectFit: 'contain' }} 
            />
        </div>
    );
};
