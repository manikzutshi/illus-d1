export interface AssetDefinition {
    component_type: string;
    visual_type: string;
    source: 'procedural' | 'glb';
    asset_url?: string;
    dimensions: { width: number; height: number; depth: number };
    anchorOffsets: Record<string, [number, number, number]>;
}

export const ASSET_REGISTRY: Record<string, AssetDefinition> = {
    'board:esp32-devkit-v1': {
        component_type: 'board:esp32-devkit-v1',
        visual_type: 'esp32',
        source: 'glb',
        asset_url: '/models/esp32.glb',
        dimensions: { width: 14, height: 1.5, depth: 10.5 },
        anchorOffsets: {}
    },
    'sensor:hc-sr04': {
        component_type: 'sensor:hc-sr04',
        visual_type: 'hcsr04',
        source: 'glb',
        asset_url: '/models/hcsr04.glb',
        dimensions: { width: 4.5, height: 3, depth: 2.5 },
        anchorOffsets: {}
    },
    'passive:resistor-tht': {
        component_type: 'passive:resistor-tht',
        visual_type: 'resistor',
        source: 'glb',
        asset_url: '/models/resistor.glb',
        dimensions: { width: 4, height: 1, depth: 1 },
        anchorOffsets: {}
    },
    'passive:led-5mm': {
        component_type: 'passive:led-5mm',
        visual_type: 'led',
        source: 'glb',
        asset_url: '/models/led.glb',
        dimensions: { width: 2, height: 3, depth: 1 },
        anchorOffsets: {}
    }
};

export function getAssetDefinition(component_type: string): AssetDefinition {
    return ASSET_REGISTRY[component_type] || {
        component_type,
        visual_type: 'unknown',
        source: 'procedural',
        dimensions: { width: 2, height: 2, depth: 2 },
        anchorOffsets: {}
    };
}
