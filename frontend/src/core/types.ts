export type Vector3 = [number, number, number];

export interface SceneGraph {
    nodes: SceneNode[];
    wires: SceneWire[];
}

export interface SceneNode {
    instance_id: string;
    component_type: string;
    transform: {
        position: Vector3;
        rotation: Vector3;
    };
    visual_type: string;
    anchors: Record<string, Vector3>; // map of pin_id to local position
    parameters: Record<string, string>;
}

export interface SceneWire {
    net_id: string;
    path: Vector3[];
    color: string;
}

// Minimal matching of the backend DesignProject schema
export interface DesignProject {
    project_id: string;
    name: string;
    components: {
        instance_id: string;
        component_type: string;
        parameters?: Record<string, string>;
        layout?: {
            x: number;
            y: number;
            z: number;
            rotation: number;
        };
    }[];
    nets: {
        net_id: string;
        connections: {
            instance_id: string;
            pin_id: string;
        }[];
        net_type?: string;
    }[];
}
