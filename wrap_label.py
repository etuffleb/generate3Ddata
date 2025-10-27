"""Wrap a label image around an imported bottle model in Blender.

This script imports the OBJ model "Bottle 2.obj", builds a thin cylindrical
sleeve that follows the bottle silhouette and applies the label image
"water-label.jpg" as a texture.  It is designed to be executed with
``blender --background --python wrap_label.py`` from the project root.
"""

from __future__ import annotations

import bpy
import math
from pathlib import Path


def clear_scene() -> None:
    """Remove all existing objects and unused datablocks from the scene."""

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    # Clear orphaned data blocks to avoid accidental reuse.
    for datablock_collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.textures,
    ):
        for datablock in list(datablock_collection):
            if datablock.users == 0:
                datablock_collection.remove(datablock)



def import_bottle(obj_path: Path) -> bpy.types.Object:
    """Import the bottle OBJ file and return the resulting object."""

    if not obj_path.exists():
        raise FileNotFoundError(f"Bottle model not found: {obj_path}")

    bpy.ops.import_scene.obj(filepath=str(obj_path))
    imported_objects = bpy.context.selected_objects
    if not imported_objects:
        raise RuntimeError("No objects were imported from the OBJ file.")

    # Join the imported pieces into a single mesh object.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported_objects[0]
    if len(imported_objects) > 1:
        bpy.ops.object.join()

    bottle = bpy.context.view_layer.objects.active
    bottle.name = "Bottle"

    # Ensure the origin is at the mesh centre and the object is centred at world origin.
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    bottle.location = (0.0, 0.0, 0.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    bpy.ops.object.shade_smooth()
    bottle.data.use_auto_smooth = True

    return bottle


def ensure_bottle_material(bottle: bpy.types.Object) -> bpy.types.Material:
    """Create a simple glossy plastic material for the bottle body."""

    material = bpy.data.materials.new(name="BottlePlastic")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs[0].default_value = (0.1, 0.35, 0.6, 1.0)
        principled.inputs[5].default_value = 0.15  # Roughness
        principled.inputs[7].default_value = 0.2   # Transmission
    bottle.data.materials.clear()
    bottle.data.materials.append(material)
    return material


def create_label_sleeve(
    bottle: bpy.types.Object,
    label_image_path: Path,
    label_height_ratio: float = 0.28,
    vertical_offset_ratio: float = 0.38,
) -> bpy.types.Object:
    """Generate a thin cylindrical mesh that hugs the bottle and carries the label."""

    if not label_image_path.exists():
        raise FileNotFoundError(f"Label image not found: {label_image_path}")

    dims = bottle.dimensions
    radius = max(dims.x, dims.y) * 0.5 * 1.02
    height = dims.z * label_height_ratio
    z_center = -dims.z * 0.5 + dims.z * vertical_offset_ratio + height / 2

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=256,
        radius=radius,
        depth=height,
        location=(0.0, 0.0, z_center),
    )
    sleeve = bpy.context.active_object
    sleeve.name = "LabelSleeve"

    # UV unwrap with cylindrical projection for even label distribution.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cylinder_project(
        direction='ALIGN_TO_OBJECT',
        align='POLAR_ZX',
        clip_to_bounds=False,
        scale_to_bounds=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")

    # Add modifiers to conform the sleeve to the bottle surface.
    shrinkwrap = sleeve.modifiers.new(name="Shrinkwrap", type='SHRINKWRAP')
    shrinkwrap.target = bottle
    shrinkwrap.wrap_method = 'NEAREST_SURFACEPOINT'
    shrinkwrap.wrap_mode = 'OUTSIDE'
    shrinkwrap.offset = 0.0015

    solidify = sleeve.modifiers.new(name="Solidify", type='SOLIDIFY')
    solidify.thickness = 0.0008
    solidify.offset = 1.0

    subdivision = sleeve.modifiers.new(name="Subdivision", type='SUBSURF')
    subdivision.levels = 2
    subdivision.render_levels = 3

    # Build the material that loads and displays the label image.
    label_material = bpy.data.materials.new(name="BottleLabel")
    label_material.use_nodes = True
    nodes = label_material.node_tree.nodes
    links = label_material.node_tree.links

    for node in list(nodes):
        if node.type not in {"OUTPUT_MATERIAL", "BSDF_PRINCIPLED"}:
            nodes.remove(node)

    principled = nodes.get("Principled BSDF")
    output = nodes.get("Material Output")

    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.inputs['Rotation'].default_value[2] = math.radians(90.0)
    mapping.inputs['Scale'].default_value[0] = 1.0
    mapping.inputs['Scale'].default_value[1] = 1.0

    tex_image = nodes.new(type="ShaderNodeTexImage")
    tex_image.image = bpy.data.images.load(str(label_image_path))
    tex_image.interpolation = 'Cubic'

    transparent = nodes.new(type="ShaderNodeBsdfTransparent")
    mix_shader = nodes.new(type="ShaderNodeMixShader")

    links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])
    links.new(tex_image.outputs['Color'], principled.inputs['Base Color'])
    links.new(tex_image.outputs['Alpha'], mix_shader.inputs['Fac'])
    links.new(transparent.outputs['BSDF'], mix_shader.inputs[1])
    links.new(principled.outputs['BSDF'], mix_shader.inputs[2])
    links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])

    principled.inputs['Specular'].default_value = 0.5
    principled.inputs['Roughness'].default_value = 0.35

    sleeve.data.materials.clear()
    sleeve.data.materials.append(label_material)

    return sleeve


def setup_camera_and_lighting(bottle: bpy.types.Object) -> None:
    """Create a simple three-point lighting setup and a frontal camera."""

    # Camera
    bpy.ops.object.camera_add(
        location=(0.0, -max(bottle.dimensions) * 3.0, bottle.dimensions.z * 0.4)
    )
    camera = bpy.context.active_object
    camera.name = "RenderCamera"
    camera.data.lens = 50
    camera.rotation_euler = (
        math.radians(75.0),
        0.0,
        0.0,
    )
    bpy.context.scene.camera = camera

    # Key light
    bpy.ops.object.light_add(type='AREA', location=(2.5, -3.0, 4.0))
    key_light = bpy.context.active_object
    key_light.data.energy = 800
    key_light.data.size = 2.0

    # Fill light
    bpy.ops.object.light_add(type='AREA', location=(-3.0, -2.0, 3.0))
    fill_light = bpy.context.active_object
    fill_light.data.energy = 300
    fill_light.data.size = 2.5

    # Rim light
    bpy.ops.object.light_add(type='AREA', location=(0.0, 3.0, 3.5))
    rim_light = bpy.context.active_object
    rim_light.data.energy = 400
    rim_light.data.size = 1.5

    # Neutral background world colour.
    world = bpy.context.scene.world
    if world and world.node_tree:
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs[0].default_value = (0.95, 0.95, 0.95, 1.0)
            background.inputs[1].default_value = 1.0



def main() -> None:
    assets_dir = Path(__file__).resolve().parent
    bottle_path = assets_dir / "Bottle 2.obj"
    label_path = assets_dir / "water-label.jpg"

    clear_scene()
    bottle = import_bottle(bottle_path)
    ensure_bottle_material(bottle)
    create_label_sleeve(bottle, label_path)
    setup_camera_and_lighting(bottle)

    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = 128
    bpy.context.scene.render.image_settings.file_format = 'PNG'


if __name__ == "__main__":
    main()
