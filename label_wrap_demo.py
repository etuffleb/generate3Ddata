import bpy
import os
import math

# === Очистка сцены ===
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# === Создание цилиндра (бутылка) ===

bpy.ops.mesh.primitive_cylinder_add(
    vertices=128,
    radius=2,
    depth=8,
    location=(0.0, 0.0, 0.0),
    end_fill_type='NGON',
)
bottle = bpy.context.active_object
bottle.name = "Bottle"

# Сглаживание: больше сегментов по высоте
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.subdivide(number_cuts=20)
bpy.ops.object.mode_set(mode='OBJECT')

# === UV-развёртка ===
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.uv.cylinder_project()
bpy.ops.object.mode_set(mode='OBJECT')

# === Создание материала и загрузка этикетки ===
mat = bpy.data.materials.new(name="LabelMaterial")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
for n in nodes:
    nodes.remove(n)

# Загружаем изображение
tex_image = nodes.new(type='ShaderNodeTexImage')
tex_image.image = bpy.data.images.load(filepath='/Users/ekaterina/Desktop/cocacola.png')  # замените путь

# Координаты и поворот этикетки
tex_coord = nodes.new(type='ShaderNodeTexCoord')
mapping = nodes.new(type='ShaderNodeMapping')

mapping.inputs['Rotation'].default_value[2] = math.radians(270)  # повернуть на 270°
mapping.inputs['Scale'].default_value[1] = 1.0     # высота полностью
mapping.inputs['Scale'].default_value[2] = 1.0     # ширина полностью
mapping.inputs['Location'].default_value[1] = 0.0  # не сдвигать


links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])

# Шейдер
bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
bsdf.inputs["Roughness"].default_value = 0.5

output = nodes.new(type='ShaderNodeOutputMaterial')
links.new(tex_image.outputs['Color'], bsdf.inputs['Base Color'])
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

bottle.data.materials.append(mat)

# === Камера ===
bpy.ops.object.camera_add(location=(0, -35, 1.5))
camera = bpy.context.active_object
camera.data.lens = 50
camera.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.camera = camera

# === Свет ===
bpy.ops.object.light_add(type='AREA', location=(0, -4, 4))
light = bpy.context.active_object
light.data.energy = 300

# === Настройки рендера ===
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.samples = 128
bpy.context.scene.render.image_settings.file_format = 'PNG'

# === Папка вывода ===
output_dir = bpy.path.abspath("//renders")
os.makedirs(output_dir, exist_ok=True)

# === Рендер под 3 ракурсами ===
angles = [240]
for angle in angles:
    bottle.rotation_euler[2] = math.radians(angle)
    bpy.context.scene.render.filepath = os.path.join(output_dir, f"render_{angle}.png")
    bpy.ops.render.render(write_still=True)
