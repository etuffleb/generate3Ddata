import bpy
import os
import math
from itertools import product
from mathutils import Vector

# === Константы для размеров ===
LABEL_IMAGE_PATH = "/path/to/label.png"  # замените на путь к изображению этикетки
LABEL_WIDTH = 2020.0
LABEL_HEIGHT = 474.0
CYLINDER_CIRCUMFERENCE = LABEL_WIDTH
CYLINDER_HEIGHT = LABEL_HEIGHT * 5.0
CYLINDER_RADIUS = CYLINDER_CIRCUMFERENCE / (2.0 * math.pi)

# === Подготовка сцены ===
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# === Создание цилиндра ===
bpy.ops.mesh.primitive_cylinder_add(
    vertices=128,
    radius=CYLINDER_RADIUS,
    depth=CYLINDER_HEIGHT,
    location=(0.0, 0.0, 0.0),
    end_fill_type='NGON',
)
bottle = bpy.context.active_object
bottle.name = "ProportionalBottle"

# Увеличим количество сегментов по высоте для корректной развёртки
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.subdivide(number_cuts=50)
bpy.ops.object.mode_set(mode='OBJECT')

# === UV-развёртка цилиндра ===
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.uv.cylinder_project()
bpy.ops.object.mode_set(mode='OBJECT')

# === Настройка материала ===
mat = bpy.data.materials.new(name="LabelMaterial")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links

# Очистка стандартных нодов
for node in list(nodes):
    nodes.remove(node)

# Ноды
tex_coord = nodes.new(type='ShaderNodeTexCoord')
tex_coord.location = (-800, 0)

mapping = nodes.new(type='ShaderNodeMapping')
mapping.location = (-600, 0)

# Располагаем этикетку по центру и задаём её высоту
scale_y = CYLINDER_HEIGHT / LABEL_HEIGHT
mapping.inputs['Scale'].default_value[1] = scale_y
mapping.inputs['Location'].default_value[1] = 0.5 - 0.5 / scale_y

tex_image = nodes.new(type='ShaderNodeTexImage')
tex_image.location = (-400, 0)
tex_image.image = bpy.data.images.load(filepath=LABEL_IMAGE_PATH)
tex_image.extension = 'CLIP'

mix_rgb = nodes.new(type='ShaderNodeMixRGB')
mix_rgb.blend_type = 'MIX'
mix_rgb.location = (-100, 0)
mix_rgb.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
bsdf.location = (100, 0)

output = nodes.new(type='ShaderNodeOutputMaterial')
output.location = (300, 0)

separate_xyz = nodes.new(type='ShaderNodeSeparateXYZ')
separate_xyz.location = (-800, -200)

math_abs = nodes.new(type='ShaderNodeMath')
math_abs.location = (-600, -200)
math_abs.operation = 'ABSOLUTE'

math_compare = nodes.new(type='ShaderNodeMath')
math_compare.location = (-400, -200)
math_compare.operation = 'LESS_THAN'
math_compare.inputs[1].default_value = LABEL_HEIGHT / 2.0

# Линки координат
links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])

# Маска по высоте с использованием координат объекта
links.new(tex_coord.outputs['Object'], separate_xyz.inputs['Vector'])
links.new(separate_xyz.outputs['Z'], math_abs.inputs[0])
links.new(math_abs.outputs[0], math_compare.inputs[0])

# Смешиваем цвет бутылки и этикетку
links.new(tex_image.outputs['Color'], mix_rgb.inputs[2])
links.new(math_compare.outputs[0], mix_rgb.inputs['Fac'])
links.new(mix_rgb.outputs['Color'], bsdf.inputs['Base Color'])
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

bottle.data.materials.append(mat)

# === Настройка камеры ===
bpy.ops.object.camera_add()
camera = bpy.context.active_object
camera.data.lens = 85
bpy.context.scene.camera = camera

# Функция для направления камеры на центр

def point_camera(obj, target):
    direction = target - obj.location
    if direction.length == 0:
        direction.z = -1
    rot_quat = direction.to_track_quat('-Z', 'Y')
    obj.rotation_euler = rot_quat.to_euler()

# === Источники света ===
bpy.ops.object.light_add(type='AREA', location=(0.0, 0.0, CYLINDER_HEIGHT))
light_top = bpy.context.active_object
light_top.data.energy = 500
light_top.data.size = CYLINDER_RADIUS * 2.0

bpy.ops.object.light_add(type='AREA', location=(0.0, 0.0, -CYLINDER_HEIGHT))
light_bottom = bpy.context.active_object
light_bottom.data.energy = 300
light_bottom.data.size = CYLINDER_RADIUS * 2.0

bpy.ops.object.light_add(type='SUN', location=(CYLINDER_RADIUS * 2.5, 0.0, CYLINDER_HEIGHT * 0.5))
sun = bpy.context.active_object
sun.data.energy = 5.0

# === Настройки рендера ===
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 128
scene.render.image_settings.file_format = 'PNG'

output_dir = bpy.path.abspath("//renders")
os.makedirs(output_dir, exist_ok=True)

# === Вычисление позиций камер по вершинам додекаэдра ===
phi = (1 + math.sqrt(5)) / 2
inv_phi = 1 / phi

dodeca_vertices = []
# Вершины (±1, ±1, ±1)
for sx, sy, sz in product((-1, 1), repeat=3):
    dodeca_vertices.append(Vector((sx, sy, sz)))

# Вершины (0, ±1/phi, ±phi) и циклические перестановки
sign_pairs = list(product((-1, 1), repeat=2))
for s1, s2 in sign_pairs:
    dodeca_vertices.append(Vector((0.0, s1 * inv_phi, s2 * phi)))
    dodeca_vertices.append(Vector((s1 * inv_phi, s2 * phi, 0.0)))
    dodeca_vertices.append(Vector((s2 * phi, 0.0, s1 * inv_phi)))

# Масштабируем вершины
bounding_radius = math.sqrt(CYLINDER_RADIUS ** 2 + (CYLINDER_HEIGHT / 2.0) ** 2)
camera_distance = bounding_radius * 2.0
scaled_vertices = [vertex.normalized() * camera_distance for vertex in dodeca_vertices]

# === Рендер для 20 ракурсов ===
origin = Vector((0.0, 0.0, 0.0))
for idx, position in enumerate(scaled_vertices):
    camera.location = position
    point_camera(camera, origin)
    scene.render.filepath = os.path.join(output_dir, f"render_{idx:02d}.png")
    bpy.ops.render.render(write_still=True)
