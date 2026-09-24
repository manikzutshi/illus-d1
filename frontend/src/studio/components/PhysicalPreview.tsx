// Experimental physical view: the pre-existing breadboard/3D pipeline fed from the same
// engineering design. It is a separate projection (Engineering Design -> physical layout),
// kept here as the foundation for the future 3D stage.
import { useMemo } from 'react';
import { Scene3D } from '../../components/Scene3D';
import { SceneBuilder } from '../../core/SceneBuilder';
import type { DesignProject } from '../../core/types';
import type { EngineeringDesign } from '../types';

export default function PhysicalPreview({ design, selected, onSelect }: {
  design: EngineeringDesign; selected: string | null; onSelect: (id: string | null) => void;
}) {
  const graph = useMemo(() => new SceneBuilder().build(design as unknown as DesignProject), [design]);
  return (
    <div className="physical">
      <Scene3D sceneGraph={graph} onSelect={onSelect} selected={selected} camView="iso" showLabels showAnchors={false} />
      <div className="physical-note">Physical placement is an early prototype (breadboard layout for a few part types). Parts without a 3D model are shown as labelled blocks.</div>
    </div>
  );
}
