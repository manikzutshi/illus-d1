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
            const x = node.transform.position[0];
            const y = node.transform.position[2]; // Using Z as Y

            if (node.component_type.includes('power_source') || node.visual_type === 'power') {
                ctx.fillStyle = 'red';
                ctx.beginPath();
                ctx.arc(x, y, 1.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = 'white';
                ctx.fillText('+V', x, y);
            } else if (node.component_type.includes('ground') || node.visual_type === 'ground') {
                ctx.strokeStyle = 'black';
                ctx.lineWidth = 0.5;
                ctx.beginPath();
                ctx.moveTo(x - 1.5, y);
                ctx.lineTo(x + 1.5, y);
                ctx.moveTo(x - 1, y + 0.5);
                ctx.lineTo(x + 1, y + 0.5);
                ctx.moveTo(x - 0.5, y + 1);
                ctx.lineTo(x + 0.5, y + 1);
                ctx.stroke();
                ctx.fillStyle = 'black';
                ctx.fillText('GND', x, y - 1);
            } else {
                let w = 5, h = 5;
                if (node.visual_type === 'board' || node.visual_type === 'esp32') { w = 12; h = 10; }
                if (node.visual_type === 'sensor' || node.visual_type === 'hcsr04') { w = 8; h = 4; }
                if (node.visual_type === 'resistor') { w = 4; h = 1.5; }
                if (node.visual_type === 'led') { w = 2.5; h = 2.5; }

                ctx.fillStyle = node.instance_id === selected ? '#e0f0ff' : '#fff';
                ctx.fillRect(x - w/2, y - h/2, w, h);
                ctx.strokeStyle = node.instance_id === selected ? '#007bff' : '#333';
                ctx.lineWidth = 0.3;
                ctx.strokeRect(x - w/2, y - h/2, w, h);

                // Draw label
                ctx.fillStyle = '#000';
                ctx.font = 'bold 0.6px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                
                let label = node.instance_id;
                let subLabel = '';
                if (node.parameters?.resistance) {
                    subLabel = `${node.parameters.resistance}`;
                } else if (node.component_type.includes('hc-sr04')) {
                    subLabel = 'Ultrasonic';
                } else if (node.component_type.includes('esp32')) {
                    subLabel = 'ESP32';
                }
                
                ctx.fillText(label, x, y - 0.4);
                if (subLabel) {
                    ctx.font = '0.4px sans-serif';
                    ctx.fillStyle = '#555';
                    ctx.fillText(subLabel, x, y + 0.4);
                }
                
                // Draw anchors (pins)
                ctx.fillStyle = 'red';
                ctx.font = '0.3px sans-serif';
                for (const [pin_id, pos] of Object.entries(node.world_anchors || node.anchors)) {
                    ctx.beginPath();
                    ctx.arc(pos[0], pos[2], 0.15, 0, Math.PI * 2);
                    ctx.fill();
                    
                    // Label the pin just outside
                    ctx.fillStyle = '#666';
                    ctx.fillText(pin_id, pos[0], pos[2] - 0.3);
                    ctx.fillStyle = 'red'; // reset for next pin
                }
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
