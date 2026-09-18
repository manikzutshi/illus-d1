import trimesh
import numpy as np
import os

def create_esp32_glb(filepath):
    # Base PCB (Black)
    pcb = trimesh.creation.box(extents=[14, 0.2, 10.5])
    pcb.visual.vertex_colors = [30, 30, 30, 255]
    pcb.apply_translation([0, 0, 0])

    # ESP Shield (Silver)
    shield = trimesh.creation.box(extents=[5, 0.4, 4])
    shield.visual.vertex_colors = [200, 200, 200, 255]
    shield.apply_translation([-3, 0.3, 0])

    # USB Port (Silver)
    usb = trimesh.creation.box(extents=[1.5, 0.5, 3])
    usb.visual.vertex_colors = [180, 180, 180, 255]
    usb.apply_translation([-6.25, 0.35, 0])

    # Headers (Black with gold pins)
    header1 = trimesh.creation.box(extents=[13, 0.3, 1])
    header1.visual.vertex_colors = [10, 10, 10, 255]
    header1.apply_translation([0, -0.25, -4.5])

    header2 = trimesh.creation.box(extents=[13, 0.3, 1])
    header2.visual.vertex_colors = [10, 10, 10, 255]
    header2.apply_translation([0, -0.25, 4.5])
    
    # Combine
    scene = trimesh.Scene([pcb, shield, usb, header1, header2])
    scene.export(filepath)

def create_hcsr04_glb(filepath):
    # PCB (Blue)
    pcb = trimesh.creation.box(extents=[4.5, 0.2, 2.5])
    pcb.visual.vertex_colors = [20, 50, 150, 255]
    
    # Transducers (Silver cylinders)
    t1 = trimesh.creation.cylinder(radius=0.8, height=1.0)
    t1.visual.vertex_colors = [180, 180, 180, 255]
    t1.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0]))
    t1.apply_translation([-1.2, 0.6, 0])

    t2 = trimesh.creation.cylinder(radius=0.8, height=1.0)
    t2.visual.vertex_colors = [180, 180, 180, 255]
    t2.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0]))
    t2.apply_translation([1.2, 0.6, 0])

    # Header
    header = trimesh.creation.box(extents=[2, 0.3, 0.5])
    header.visual.vertex_colors = [10, 10, 10, 255]
    header.apply_translation([0, -0.25, 1.0])

    scene = trimesh.Scene([pcb, t1, t2, header])
    scene.export(filepath)

def create_resistor_glb(filepath):
    # Body (Beige)
    body = trimesh.creation.cylinder(radius=0.15, height=1.5)
    body.visual.vertex_colors = [210, 180, 140, 255]
    body.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 0, 1]))

    # Wire leads (Silver)
    lead1 = trimesh.creation.cylinder(radius=0.03, height=1.5)
    lead1.visual.vertex_colors = [150, 150, 150, 255]
    lead1.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 0, 1]))
    lead1.apply_translation([-1.5, 0, 0])

    lead2 = trimesh.creation.cylinder(radius=0.03, height=1.5)
    lead2.visual.vertex_colors = [150, 150, 150, 255]
    lead2.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 0, 1]))
    lead2.apply_translation([1.5, 0, 0])
    
    # Strip 1
    band1 = trimesh.creation.cylinder(radius=0.16, height=0.15)
    band1.visual.vertex_colors = [255, 0, 0, 255]
    band1.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 0, 1]))
    band1.apply_translation([-0.5, 0, 0])

    # Strip 2
    band2 = trimesh.creation.cylinder(radius=0.16, height=0.15)
    band2.visual.vertex_colors = [0, 0, 0, 255]
    band2.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 0, 1]))
    band2.apply_translation([0, 0, 0])
    
    scene = trimesh.Scene([body, lead1, lead2, band1, band2])
    scene.export(filepath)

def create_led_glb(filepath):
    # Base (Red transparent-ish, using solid for now)
    base = trimesh.creation.cylinder(radius=0.25, height=0.3)
    base.visual.vertex_colors = [255, 0, 0, 150]
    base.apply_translation([0, 0.15, 0])
    
    dome = trimesh.creation.icosphere(radius=0.25, subdivisions=3)
    dome.visual.vertex_colors = [255, 0, 0, 150]
    dome.apply_translation([0, 0.3, 0])
    
    # Leads
    lead1 = trimesh.creation.cylinder(radius=0.03, height=1.0)
    lead1.visual.vertex_colors = [150, 150, 150, 255]
    lead1.apply_translation([0.1, -0.5, 0])

    lead2 = trimesh.creation.cylinder(radius=0.03, height=1.0)
    lead2.visual.vertex_colors = [150, 150, 150, 255]
    lead2.apply_translation([-0.1, -0.5, 0])

    scene = trimesh.Scene([base, dome, lead1, lead2])
    scene.export(filepath)

def create_breadboard_glb(filepath):
    # Main body
    board = trimesh.creation.box(extents=[34, 0.8, 19])
    board.visual.vertex_colors = [240, 240, 240, 255]
    
    # Trench
    trench = trimesh.creation.box(extents=[32, 0.2, 1])
    trench.visual.vertex_colors = [50, 50, 50, 255]
    trench.apply_translation([0, 0.35, 0])
    
    # Rails
    rail_b1 = trimesh.creation.box(extents=[32, 0.05, 0.2])
    rail_b1.visual.vertex_colors = [0, 0, 255, 255]
    rail_b1.apply_translation([0, 0.4, -7.5])
    
    rail_r1 = trimesh.creation.box(extents=[32, 0.05, 0.2])
    rail_r1.visual.vertex_colors = [255, 0, 0, 255]
    rail_r1.apply_translation([0, 0.4, -8.5])

    rail_b2 = trimesh.creation.box(extents=[32, 0.05, 0.2])
    rail_b2.visual.vertex_colors = [0, 0, 255, 255]
    rail_b2.apply_translation([0, 0.4, 7.5])
    
    rail_r2 = trimesh.creation.box(extents=[32, 0.05, 0.2])
    rail_r2.visual.vertex_colors = [255, 0, 0, 255]
    rail_r2.apply_translation([0, 0.4, 8.5])

    scene = trimesh.Scene([board, trench, rail_b1, rail_r1, rail_b2, rail_r2])
    scene.export(filepath)

if __name__ == '__main__':
    out_dir = 'frontend/public/models'
    os.makedirs(out_dir, exist_ok=True)
    create_esp32_glb(os.path.join(out_dir, 'esp32.glb'))
    create_hcsr04_glb(os.path.join(out_dir, 'hcsr04.glb'))
    create_resistor_glb(os.path.join(out_dir, 'resistor.glb'))
    create_led_glb(os.path.join(out_dir, 'led.glb'))
    create_breadboard_glb(os.path.join(out_dir, 'breadboard.glb'))
    print("GLB models generated.")
