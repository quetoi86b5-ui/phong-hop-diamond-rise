"""Run with Python 3.13, bpy 5.2.5 and Pillow. Output is kept outside the site."""

import argparse
import math
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont


WIDTH, LENGTH, HEIGHT = 4.0, 5.0, 2.85
TABLE_X, TABLE_Y = 1.15, 2.80
DOOR_CENTER, DOOR_WIDTH = -0.35, 1.50
DOOR_Y = (DOOR_CENTER - DOOR_WIDTH / 2, DOOR_CENTER + DOOR_WIDTH / 2)
CHAIRS = [(x, y) for x in (-0.83, 0.83) for y in (-0.94, 0, 0.94)]
VIEWS = [
    ("Logo & bằng khen", (-1.70, 0.25, 1.63), (1.95, -0.12, 1.37)),
    ("Điều hòa & lam gỗ", (0.12, -2.17, 1.59), (-0.06, 2.47, 1.36)),
    ("Cửa & hốc trưng bày", (1.70, -0.15, 1.62), (-1.98, 0.40, 1.43)),
    ("Bảng viết", (0.02, 2.18, 1.60), (-0.22, -2.48, 1.36)),
]


def rgb(hex_value):
    srgb = [int(hex_value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in srgb)


def finish(name, color, roughness=0.5, metal=0, emission=0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*rgb(color), 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = material.diffuse_color
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metal
    if emission:
        shader.inputs['Emission Color'].default_value = material.diffuse_color
        shader.inputs['Emission Strength'].default_value = emission
    return material


def texture(material, colors, stretch, scale, bump, marble=False):
    nodes = material.node_tree.nodes
    link = material.node_tree.links.new
    coords = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeVectorMath')
    mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = stretch
    link(coords.outputs['Generated'], mapping.inputs[0])
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = 3.2
    link(mapping.outputs['Vector'], noise.inputs['Vector'])
    source = noise.outputs['Fac']
    if marble:
        waves = nodes.new('ShaderNodeTexWave')
        waves.wave_type = 'BANDS'
        waves.bands_direction = 'DIAGONAL'
        waves.inputs['Scale'].default_value = 1.9
        waves.inputs['Distortion'].default_value = 7
        waves.inputs['Detail Scale'].default_value = 2.2
        link(mapping.outputs['Vector'], waves.inputs['Vector'])
        source = waves.outputs['Fac']
    ramp = nodes.new('ShaderNodeValToRGB')
    for position, color in colors:
        if position == colors[0][0]:
            stop = ramp.color_ramp.elements[0]
        elif position == colors[-1][0]:
            stop = ramp.color_ramp.elements[-1]
        else:
            stop = ramp.color_ramp.elements.new(position)
        stop.position = position
        stop.color = (*rgb(color), 1)
    shader = nodes.get('Principled BSDF')
    link(source, ramp.inputs['Fac'])
    link(ramp.outputs['Color'], shader.inputs['Base Color'])
    relief = nodes.new('ShaderNodeBump')
    relief.inputs['Strength'].default_value = 0.23
    relief.inputs['Distance'].default_value = bump
    link(noise.outputs['Fac'], relief.inputs['Height'])
    link(relief.outputs['Normal'], shader.inputs['Normal'])


def block(name, center, size, material, bevel=0.005):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        edges = obj.modifiers.new('Rounded edges', 'BEVEL')
        edges.width = bevel
        edges.segments = 3
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def pipe(name, points, radius, material, closed=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for point, xyz in zip(spline.points, points):
        point.co = (*xyz, 1)
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def light(name, location, look_at, power, size, color, width=None):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.color = color
    data.size = size
    if width:
        data.shape = 'RECTANGLE'
        data.size_y = width
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(look_at) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def text_on_logo(text, y, z, size, material, font):
    bpy.ops.object.text_add(location=(WIDTH / 2 - 0.16, y, z))
    obj = bpy.context.object
    obj.name = text
    obj.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
    obj.data.body = text
    obj.data.size = size
    obj.data.extrude = 0.003
    obj.data.align_x = 'CENTER'
    if font:
        obj.data.font = font
    obj.data.materials.append(material)
    bpy.ops.object.convert(target='MESH')


def find_font(*names):
    for folder in (Path('C:/Windows/Fonts'), Path('/usr/share/fonts/truetype/dejavu')):
        for name in names:
            path = folder / name
            if path.is_file():
                return str(path)


def build_room():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 14
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_x, scene.render.resolution_y = 810, 1080
    scene.world = bpy.data.worlds.new('Ambient')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value = 0.24
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = -0.31

    wood = finish('Vertical walnut veneer', '865f43', 0.39)
    texture(wood, [(0.10, '483023'), (0.52, '735039'), (0.90, '9e7150')], (14, 14, 0.32), 5, 0.009)
    desk = finish('Oak desktop', 'ae7950', 0.4)
    texture(desk, [(0.13, '88593a'), (0.49, 'b58254'), (0.88, 'c99a68')], (12, 0.40, 4), 6, 0.008)
    stone = finish('Honed cream marble', 'e9dcc7', 0.29)
    texture(stone, [(0.0, 'bda491'), (0.041, 'dbccba'), (0.13, 'e8d8bc'), (1, 'efe4d3')], (0.85, 1.08, 0.80), 3, 0.006, marble=True)
    carpet = finish('Greige carpet tiles', '8b8176', 0.89)
    texture(carpet, [(0.06, '6f6357'), (0.51, '8c7f73'), (0.90, 'a09688')], (1, 1, 1), 360, 0.018)
    paint = finish('Warm white paint', 'eee8dc', 0.78)
    brass = finish('Champagne brass', 'bd945d', 0.29, 0.70)
    dark = finish('Black mesh and steel', '302b2a', 0.62)
    trim = finish('Warm white aluminum', 'd7d4cb', 0.32, 0.14)
    glass = finish('Frosted glass', '8b988f', 0.25, 0.13)
    board = finish('Matte white writing surface', 'f2efea', 0.35)
    navy = finish('Raised navy lettering', '182d42', 0.35)
    led = finish('Warm LED diffuser', 'ffe3bf', 0.23, emission=2.7)
    hall = finish('Hallway finish', '5d554d', 0.76)
    paper = finish('Certificate paper', 'e5d6ad', 0.68)

    x, y = WIDTH / 2, LENGTH / 2
    block('Carpet', (0, 0, -0.035), (WIDTH, LENGTH, 0.07), carpet, 0)
    block('Ceiling', (0, 0, HEIGHT + 0.065), (WIDTH + 0.13, LENGTH + 0.13, 0.13), paint, 0)
    for edge in (-1, 1):
        block('Ceiling perimeter beam', (edge * (x - 0.06), 0, HEIGHT - 0.09), (0.12, LENGTH, 0.18), paint)
        block('Ceiling perimeter beam', (0, edge * (y - 0.06), HEIGHT - 0.09), (WIDTH - 0.24, 0.12, 0.18), paint)
        block('End wall', (0, edge * (y + 0.055), HEIGHT / 2), (WIDTH + 0.15, 0.11, HEIGHT), wood, 0)
        block('Skirting', (0, edge * (y - 0.025), 0.032), (WIDTH, 0.045, 0.065), brass)
    block('East wall', (x + 0.055, 0, HEIGHT / 2), (0.11, LENGTH, HEIGHT), wood, 0)
    for start, end in ((-y, DOOR_Y[0]), (DOOR_Y[1], y)):
        block('West walnut wall', (-x - 0.055, (start + end) / 2, HEIGHT / 2), (0.11, end - start, HEIGHT), wood, 0)
        block('West skirting', (-x + 0.024, (start + end) / 2, 0.032), (0.041, end - start, 0.065), brass)
    block('Door header', (-x, DOOR_CENTER, 2.70), (0.14, DOOR_WIDTH, 0.31), wood)
    for offset in (0, DOOR_WIDTH / 2, DOOR_WIDTH):
        block('Door upright', (-x + 0.015, DOOR_Y[0] + offset, 1.27), (0.09, 0.035, 2.54), trim)
    for z in (0.018, 0.77, 1.22, 2.13, 2.54):
        span = DOOR_WIDTH if z in (2.13, 2.54) else DOOR_WIDTH / 2
        center = DOOR_CENTER if z in (2.13, 2.54) else DOOR_CENTER + DOOR_WIDTH / 4
        block('Door rail', (-x + 0.015, center, z), (0.085, span, 0.033), trim)
    block('Frosted sliding leaf', (-x, DOOR_CENTER + DOOR_WIDTH / 4, 1.07), (0.026, DOOR_WIDTH / 2, 2.08), glass)
    block('Frosted transom', (-x, DOOR_CENTER, 2.33), (0.026, DOOR_WIDTH, 0.38), glass)
    block('Hall floor', (-2.65, DOOR_CENTER, -0.045), (1.35, 1.75, 0.08), hall)
    block('Hall back wall', (-3.28, DOOR_CENTER, 1.25), (0.10, 1.8, 2.5), hall)
    block('Hall side wall', (-2.62, DOOR_CENTER - 0.89, 1.25), (1.32, 0.12, 2.5), hall)

    # Built-ins share the same heights and veneer. Each corner is present in every camera.
    for sign in (-1, 1):
        block('End wall lower cabinet', (0, sign * (y - 0.16), 0.37), (3.73, 0.31, 0.70), wood)
    block('Logo wall lower cabinet', (x - 0.16, 0, 0.37), (0.31, 4.72, 0.70), wood)
    block('Marble feature wall', (x - 0.105, 0, 1.61), (0.075, 3.68, 1.64), stone)
    block('Logo wall top light', (x - 0.148, 0, 2.451), (0.015, 3.66, 0.011), led)
    block('Logo wall bottom light', (x - 0.151, 0, 0.775), (0.015, 3.66, 0.011), led)
    light('Marble wash', (x - 0.47, 0.06, 2.46), (x - 0.02, 0.06, 1.45), 51, 2.9, (1, 0.82, 0.64), 0.14)

    def shelf(center, r, width, height, axis, certificates=False):
        def part(name, u, z, depth, span, thick, material):
            if axis == 'east':
                block(name, (x - depth, u, z), (0.22, span, thick), material)
            else:
                edge = y - depth if axis == 'north' else -y + depth
                block(name, (u, edge, z), (span, 0.23, thick), material)
        for side in (-1, 1):
            part('Shelf side', center + side * width / 2, r, 0.14, 0.038, height, wood)
        for level in range(4):
            z = r - height / 2 + level * height / 3
            part('Walnut shelf', center, z, 0.14, width, 0.04, wood)
            if level:
                if axis == 'east':
                    block('Recessed shelf LED', (x - 0.23, center, z - 0.025), (0.012, width - 0.05, 0.012), led)
                else:
                    at = y - 0.23 if axis == 'north' else -y + 0.23
                    block('Recessed shelf LED', (center, at, z - 0.025), (width - 0.05, 0.012, 0.012), led)
            if certificates and level < 3:
                block('Certificate frame', (x - 0.132, center, z + 0.196), (0.028, 0.235, 0.31), brass)
                block('Certificate', (x - 0.150, center, z + 0.196), (0.012, 0.199, 0.272), paper)
                for line in range(4):
                    block('Certificate detail', (x - 0.157, center, z + 0.161 + line * 0.032), (0.001, 0.122, 0.0035), brass, 0)

    for side in (-1, 1):
        shelf(side * 2.11, 1.61, 0.43, 1.65, 'east', True)
        shelf(side * 1.61, 1.59, 0.42, 1.61, 'north')
    shelf(1.60, 1.59, 0.42, 1.61, 'south')
    for i in range(47):
        block('Walnut slat', ((i - 23) * 0.057, y - 0.084, 1.56), (0.033, 0.052, 1.54), wood, 0.003)
    block('AC chase', (0, y - 0.065, 2.452), (2.85, 0.117, 0.12), wood)
    block('Air conditioner', (-0.68, y - 0.145, 2.37), (0.89, 0.25, 0.225), trim, 0.035)
    block('AC louver', (-0.68, y - 0.273, 2.31), (0.73, 0.015, 0.028), dark)
    block('Slat wall LED', (0, y - 0.12, 2.322), (2.65, 0.014, 0.013), led)
    block('Slat wall bottom LED', (0, y - 0.115, 0.789), (2.65, 0.014, 0.013), led)
    light('Slat wash', (0, y - 0.4, 2.40), (0, y, 1.48), 48, 2.56, (1, 0.79, 0.57), 0.105)

    block('Writing board frame', (-0.17, -y + 0.068, 1.61), (2.27, 0.084, 1.075), brass, 0.017)
    block('Writing board', (-0.17, -y + 0.118, 1.61), (2.22, 0.026, 1.02), board, 0.008)
    block('Marker shelf', (-0.77, -y + 0.15, 1.058), (0.83, 0.082, 0.023), trim)
    block('Board wall LED', (0, -y + 0.104, 2.419), (3.13, 0.016, 0.012), led)
    light('Board wall wash', (0.06, -y + 0.44, 2.48), (0.06, -y, 1.6), 55, 2.65, (1, 0.83, 0.66), 0.12)

    for i, z in enumerate((0.90, 1.44, 2.06)):
        middle = DOOR_Y[1] + 0.26 + (i == 2) * 0.40
        block('Champagne niche surround', (-x + 0.08, middle, z), (0.12, 0.35, 0.37), brass)
        block('Recess appearance walnut', (-x + 0.146, middle, z), (0.017, 0.303, 0.319), wood)
        block('Niche warm light', (-x + 0.158, middle, z + 0.142), (0.023, 0.273, 0.015), led)
        block('Display object', (-x + 0.161, middle, z - 0.06), (0.037, 0.088, 0.133), paper, 0.024)

    font_file = find_font('timesbd.ttf', 'DejaVuSerif-Bold.ttf')
    font = bpy.data.fonts.load(font_file) if font_file else None
    text_on_logo('DIAMOND RISE', -0.12, 1.66, 0.27, navy, font)
    text_on_logo('Accounting  •  Legal  •  Consulting', -0.12, 1.44, 0.112, navy, None)
    # The only brand mark is on the east wall.
    ly, lz = 1.13, 1.73
    ring = [(x - 0.153, ly + .085 * math.cos(i * math.tau / 48), lz + .085 * math.sin(i * math.tau / 48)) for i in range(48)]
    pipe('Brass emblem ring', ring, 0.006, brass, closed=True)
    for i in range(20):
        angle = i * math.tau / 20
        radius = .155 if i % 2 == 0 else .128
        pipe('Brass emblem ray', [(x - 0.153, ly + r * math.cos(angle), lz + r * math.sin(angle)) for r in (.092, radius)], .004, brass)

    block('Existing conference table', (0, 0, 0.753), (TABLE_X, TABLE_Y, 0.066), desk, 0.034)
    for side in (-1, 1):
        block('Table leg assembly', (0, side * 1.13, 0.357), (0.96, 0.072, 0.69), dark)
        block('Table steel foot', (0, side * 1.13, 0.045), (1.02, 0.10, 0.048), dark)
        block('Cable pass-through', (0, side * 0.65, 0.787), (0.145, 0.072, 0.006), dark)
    for sx, sy in CHAIRS:
        direction = 1 if sx > 0 else -1
        block('Chair padded seat', (sx, sy, 0.47), (0.45, 0.47, 0.07), dark, 0.043)
        back = block('Chair mesh back', (sx + direction * 0.22, sy, 0.79), (0.055, 0.46, 0.58), dark, 0.023)
        back.rotation_euler.y = direction * 0.095
        pipe('Chair lift', [(sx, sy, 0.12), (sx, sy, 0.44)], 0.034, dark)
        for i in range(5):
            t = i * math.tau / 5
            tip = (sx + .27 * math.cos(t), sy + .27 * math.sin(t), .071)
            pipe('Chair base spoke', [(sx, sy, .115), tip], .013, trim)
            block('Caster', (tip[0], tip[1], .046), (.055, .042, .052), dark, .011)
        for arm in (-1, 1):
            pair = sy + arm * .236
            pipe('Chair arm frame', [(sx + direction * .02, pair, .48), (sx + direction * .02, pair, .65), (sx - direction * .17, pair, .65)], .016, dark)

    # A single fixture and fixed ceiling lights serve all views.
    corners = [(0.18, 0.79, 0), (-0.18, 0.79, 90), (-0.18, -0.79, 180), (0.18, -0.79, 270)]
    def oval(z):
        return [(a + .19 * math.cos(math.radians(start + i * 10)), b + .19 * math.sin(math.radians(start + i * 10)), z)
                for a, b, start in corners for i in range(10)]
    pipe('Champagne suspended fixture', oval(2.53), 0.037, brass, True)
    pipe('Continuous diffuser', oval(2.50), 0.020, led, True)
    for side in (-1, 1):
        pipe('Pendant cable', [(0, side * .69, 2.54), (0, side * .69, HEIGHT)], .004, brass)
    block('Pendant canopy', (0, 0, HEIGHT - 0.021), (.17, 1.57, .044), brass)
    light('Pendant task light', (0, 0, 2.47), (0, 0, 0.71), 123, .62, (1, .91, .79), 1.68)
    for sx in (-1.03, 1.03):
        for sy in (-1.60, 1.60):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.049, depth=.013, location=(sx, sy, HEIGHT - .013))
            bpy.context.object.name = 'Ceiling downlight diffuser'
            bpy.context.object.data.materials.append(led)
            light('Ceiling downlight', (sx, sy, HEIGHT - .030), (sx, sy, 0), 65, .30, (1, .91, .82))
    light('Room fill', (0.12, .35, 2.69), (0, 0, 0), 82, 2.0, (1, .94, .88), 2.0)

    cameras = []
    for label, eye, subject in VIEWS:
        data = bpy.data.cameras.new(label)
        data.lens = 20
        data.sensor_fit = 'HORIZONTAL'
        data.clip_start = 0.04
        camera = bpy.data.objects.new(label, data)
        bpy.context.collection.objects.link(camera)
        camera.location = eye
        camera.rotation_euler = (Vector(subject) - camera.location).to_track_quat('-Z', 'Y').to_euler()
        cameras.append(camera)
    scene.camera = cameras[0]
    return scene, cameras


def draw_plan(path):
    image = Image.new('RGB', (1440, 1120), '#211c19')
    pen = ImageDraw.Draw(image)
    regular = find_font('segoeui.ttf', 'DejaVuSans.ttf')
    bold = find_font('segoeuib.ttf', 'DejaVuSans-Bold.ttf')
    def label(place, text, size=24, color='#e9e0d4', strong=False, anchor='la'):
        font = ImageFont.truetype(bold if strong else regular, size) if regular and bold else ImageFont.load_default(size=size)
        pen.text(place, text, fill=color, font=font, anchor=anchor)
    def point(x, y):
        return (465 + x * 153, 632 - y * 153)
    def rect(x0, y0, x1, y1, fill, outline=None, width=2):
        pen.rectangle([point(x0, y1), point(x1, y0)], fill=fill, outline=outline, width=width)
    def line(a, b, color='#aa916c', width=3):
        pen.line([point(*a), point(*b)], fill=color, width=width)
    def arrow(a, b):
        line(a, b, '#f9e8ae', 3)
        angle = math.atan2(b[1]-a[1], b[0]-a[0])
        tip = [point(*b)] + [point(b[0] - .105 * math.cos(angle+i), b[1] - .105 * math.sin(angle+i)) for i in (-.50, .50)]
        pen.polygon(tip, fill='#f9e8ae')

    label((76, 53), 'Mặt bằng PA 04', 48, strong=True)
    label((78, 117), 'Phòng họp Diamond Rise · Kích thước giả định', 27, '#d8ba88')
    x, y = WIDTH / 2, LENGTH / 2
    rect(-x, -y, x, y, '#73695f')
    for j in range(1, 10):
        p = -y + j * 0.50
        line((-x, p), (x, p), '#7c7165', 1)
    for j in range(1, 8):
        p = -x + j * .50
        line((p, -y), (p, y), '#7c7165', 1)
    line((-x, y), (x, y), '#dfc59a', 9)
    line((x, y), (x, -y), '#dfc59a', 9)
    line((x, -y), (-x, -y), '#dfc59a', 9)
    line((-x, y), (-x, DOOR_Y[1]), '#dfc59a', 9)
    line((-x, DOOR_Y[0]), (-x, -y), '#dfc59a', 9)
    line((-x, DOOR_CENTER), (-x, DOOR_Y[1]), '#a9c7c2', 8)
    line((-x - .09, DOOR_Y[0]), (-x - .09, DOOR_Y[1]), '#a9c7c2', 3)
    rect(x-.31, -y+.13, x, y-.13, '#a47751')
    rect(x-.22, -1.83, x-.07, 1.83, '#e2d2b5')
    rect(-x+.13, y-.31, x-.31, y, '#a47751')
    rect(-1.36, y-.24, 1.36, y-.09, '#c38c5e')
    rect(-1.16, y-.23, -.22, y-.075, '#e1ddd3')
    rect(-x+.13, -y, x-.31, -y+.31, '#a47751')
    rect(-1.29, -y+.10, .94, -y+.19, '#eee9df')
    for i in range(3):
        mid = DOOR_Y[1] + .26 + (i == 2) * .40
        rect(-x+.02, mid-.14, -x+.14, mid+.14, '#c29c66')
    rect(-TABLE_X/2, -TABLE_Y/2, TABLE_X/2, TABLE_Y/2, '#b98558', '#dfb588', 4)
    label(point(0, 0), 'Bàn họp', 24, '#231a13', True, 'mm')
    for cx, cy in CHAIRS:
        pen.rounded_rectangle([point(cx-.215, cy+.222),point(cx+.215,cy-.222)], radius=11, fill='#332e2c', outline='#b19e86', width=2)
    for i,(name, eye, destination) in enumerate(VIEWS, 1):
        a = eye[:2]
        dx, dy = destination[0]-a[0], destination[1]-a[1]
        span = math.hypot(dx,dy)
        nx, ny = dx / span, dy / span
        arrow((a[0]+nx*.20,a[1]+ny*.20), (a[0]+nx*.52,a[1]+ny*.52))
        px, py = point(*a)
        pen.ellipse([px-16,py-16,px+16,py+16], fill='#332821', outline='#f9e8ae',width=2)
        label((px,py),str(i),19,'#fff0c3',True,'mm')
    line((-x, y+.22), (x, y+.22))
    for side in (-1, 1):
        line((side*x,y+.17),(side*x,y+.27))
    label(point(0, y+.36), '≈ 4,00 m', 25, '#e8c799', True, 'mm')
    line((x+.26,-y),(x+.26,y))
    for side in (-1, 1):
        line((x+.21,side*y),(x+.31,side*y))
    label(point(x+.37, .28), '≈ 5,00 m', 24, '#e8c799', True)
    label((897, 225), 'Vị trí và hướng nhìn', 32, strong=True)
    for i, (title, _, _) in enumerate(VIEWS, 1):
        yy = 310 + (i-1)*113
        pen.ellipse((900, yy, 943, yy+43), fill='#443428', outline='#d1aa73', width=2)
        label((921, yy+21), str(i), 22, '#fff0c3', True, 'mm')
        label((967, yy+10), title, 25, strong=True)
    label((902, 789), 'Thảm tấm xám nâu', 24)
    label((902, 830), 'Bàn và cửa theo ảnh hiện trạng', 24)
    label((78, 1049), 'Mặt bằng bố trí sơ bộ · Cần đo hiện trạng trước khi thi công.', 24, '#d8ba88')
    image.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--views', type=int, nargs='+', choices=range(1, 5), default=list(range(1, 5)))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    draw_plan(args.output / 'pa04-mat-bang.png')
    scene, cameras = build_room()
    if args.quick:
        scene.render.resolution_percentage = 55
        scene.cycles.samples = 8
    else:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str((args.output / 'pa04-mo-hinh.blend').resolve()))
    for angle in args.views:
        scene.camera = cameras[angle - 1]
        scene.render.filepath = str((args.output / f'pa04-model-goc-{angle}.png').resolve())
        bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
