#!/usr/bin/env python3
"""
EMERGENCY FIX - Blender batch render for NON-TEXTURED models
Forces GPU-only rendering and limits CPU usage to not interfere with other users

Usage:
  CUDA_VISIBLE_DEVICES=3 blender --background --threads 4 --python mamba_render_EMERGENCY_FIX.py
"""

import bpy
import math
import random
from pathlib import Path
from mathutils import Vector
from datetime import datetime
import traceback
import sys
import os
import hashlib

# ============================================================================
# CRITICAL FIX: Limit CPU threads IMMEDIATELY
# ============================================================================
# Limit Blender to use only 4 CPU threads (out of 28 available)
bpy.context.scene.render.threads_mode = 'FIXED'
bpy.context.scene.render.threads = 6  # Use only 4 CPU threads

print("=" * 80)
print("EMERGENCY MODE: CPU threads limited to 4")
print("This prevents blocking other users on the server")
print("=" * 80)

# ============================================================================
# CONFIGURATION PARAMETERS
# ============================================================================

# Input/Output paths (Server paths)
INPUT_DIR = Path("/mnt/hd2/29d_kon/projects/Rendering/Dataset/MeshMambaSaliency/MeshFile/rgb_texture")
OUTPUT_DIR = Path("/mnt/hd2/29d_kon/projects/Rendering/Mamba_2/rgb_textured_videos")
LOG_DIR = Path("/mnt/hd2/29d_kon/projects/Rendering/Mamba_2/logs")

# Bounding box constraints for model (in meters)
BBOX_MAX_WIDTH  = 0.8
BBOX_MAX_DEPTH  = 0.8
BBOX_MAX_HEIGHT = 0.7

# Scene settings
H_EYE = 0.0
CAMERA_DISTANCE = 1.5
SPHERE_RADIUS = 5.0

# Animation settings
FPS = 30
DURATION_SECONDS = 17 # Reduced from 36
DEG_PER_SECOND = 24.0
SEED = None

# Render settings - OPTIMIZED for GPU without overloading
RESOLUTION_X = 1920
RESOLUTION_Y = 1080
SAMPLES = 160 # Reduced from 196 - still good quality with denoising
USE_DENOISING = True
USE_PERSISTENT_DATA = True

# Lighting for NON-TEXTURED models
EMISSION_COLOR = (0.70, 0.70, 0.70)
EMISSION_STRENGTH = 1.0
RIM_LIGHT_STRENGTH = 0.0  # Disabled

# параметризация освещения
EXPOSURE = 0.0  # Уменьшите до -0.5 или -1.0 если модели всё равно пересвечены
VIEW_TRANSFORM = 'Standard'

# ============================================================================
# GLOBAL STATE
# ============================================================================

_log_file = None
_error_log_file = None
_progress_log_file = None
_gpu_enabled = False

# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

def init_logging():
    """Initialize log files."""
    global _log_file, _error_log_file, _progress_log_file

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Main log
    log_path = LOG_DIR / f"batch_render_EMERGENCY_{timestamp}.log"
    _log_file = open(log_path, 'w', encoding='utf-8')

    # Error log
    error_log_path = LOG_DIR / f"batch_render_EMERGENCY_errors_{timestamp}.log"
    _error_log_file = open(error_log_path, 'w', encoding='utf-8')

    # Progress log
    progress_log_path = LOG_DIR / f"batch_render_EMERGENCY_progress_{timestamp}.log"
    _progress_log_file = open(progress_log_path, 'w', encoding='utf-8')

    log("=" * 80)
    log("EMERGENCY FIX - BATCH RENDER NON-TEXTURED MODELS")
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"CPU THREADS LIMITED TO: 4 (to prevent server overload)")
    log(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'Not set')}")
    log(f"Input: {INPUT_DIR}")
    log(f"Output: {OUTPUT_DIR}")
    log("=" * 80)

def close_logging():
    """Close log files."""
    global _log_file, _error_log_file, _progress_log_file
    if _log_file:
        _log_file.close()
    if _error_log_file:
        _error_log_file.close()
    if _progress_log_file:
        _progress_log_file.close()

def log(message):
    """Print log message to console and main log file."""
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
    print(formatted)
    if _log_file:
        _log_file.write(formatted + "\n")
        _log_file.flush()

def log_error(message, exception=None):
    """Log error message to error log file."""
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {message}"
    print(formatted)
    if _error_log_file:
        _error_log_file.write(formatted + "\n")
        if exception:
            _error_log_file.write(traceback.format_exc() + "\n")
        _error_log_file.flush()

def log_progress(current, total, model_name, status):
    """Log progress to progress log file."""
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] [{current}/{total}] {model_name}: {status}"
    print(formatted)
    if _progress_log_file:
        _progress_log_file.write(formatted + "\n")
        _progress_log_file.flush()

# ============================================================================
# CRITICAL: GPU SETUP WITH FALLBACK PREVENTION
# ============================================================================

def force_gpu_only():
    """Force GPU-only rendering, fail if GPU not available."""
    global _gpu_enabled
    
    log("Forcing GPU-only rendering...")
    
    # Set Cycles engine
    bpy.context.scene.render.engine = 'CYCLES'
    
    # CRITICAL: Limit CPU threads
    bpy.context.scene.render.threads_mode = 'FIXED'
    bpy.context.scene.render.threads = 4
    log("CPU threads limited to 4")
    
    # Enable persistent data for GPU
    bpy.context.scene.render.use_persistent_data = True
    
    # Get Cycles preferences
    prefs = bpy.context.preferences
    cycles_prefs = prefs.addons['cycles'].preferences
    cycles_prefs.refresh_devices()
    
    gpu_found = False
    
    # Try OPTIX first, then CUDA
    for compute_type in ['OPTIX', 'CUDA']:
        try:
            cycles_prefs.compute_device_type = compute_type
            devices = list(cycles_prefs.devices)
            
            log(f"Checking {compute_type} devices...")
            
            # Disable ALL CPU devices, enable ALL GPU devices
            for device in devices:
                if device.type == 'CPU':
                    device.use = False
                    log(f"  DISABLED: {device.name} (CPU)")
                else:
                    device.use = True
                    gpu_found = True
                    log(f"  ENABLED: {device.name} (GPU)")
            
            if gpu_found:
                # FORCE GPU device
                bpy.context.scene.cycles.device = 'GPU'
                
                # Verify it's set
                if bpy.context.scene.cycles.device == 'GPU':
                    log(f"SUCCESS: GPU rendering enabled with {compute_type}")
                    _gpu_enabled = True
                    return True
                else:
                    log("WARNING: GPU setting did not apply!")
                    
        except Exception as e:
            log(f"  {compute_type} error: {str(e)}")
            continue
    
    # CRITICAL: Do not allow CPU fallback
    if not gpu_found:
        log("CRITICAL ERROR: No GPU found!")
        log("Aborting to prevent CPU overload.")
        log("Please check:")
        log("  1. CUDA_VISIBLE_DEVICES=1 is set")
        log("  2. Blender has CUDA/OptiX support")
        log("  3. GPU #3 is available")
        sys.exit(1)
    
    return False

def verify_gpu_before_render():
    """Verify GPU is active before each render."""
    if not _gpu_enabled:
        log("CRITICAL: GPU not enabled, attempting to force...")
        if not force_gpu_only():
            log("ABORTING: Cannot render without GPU")
            sys.exit(1)
    
    # Double-check GPU is still active
    scene = bpy.context.scene
    if scene.cycles.device != 'GPU':
        log("WARNING: GPU was disabled, re-enabling...")
        scene.cycles.device = 'GPU'
        scene.render.use_persistent_data = True
        
        # Limit threads again
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 4
        
        if scene.cycles.device != 'GPU':
            log("CRITICAL: Cannot enable GPU!")
            log("Aborting to prevent CPU overload")
            sys.exit(1)

# функция создания сида зависящего от названяи .obj файла:
def generate_seed_from_filename(filename):
    """
    Генерирует воспроизводимый seed из имени файла.
    Работает одинаково на разных операционных системах.
    НЕ зависит от регистра букв.
    
    Args:
        filename: Имя файла модели (строка)
    
    Returns:
        int: Seed для random/numpy в диапазоне [0, 2^31-1]
    """
    # ПРИВОДИМ К НИЖНЕМУ РЕГИСТРУ для независимости от регистра
    filename_normalized = filename.lower()
    # Преобразуем имя файла в байты (UTF-8)
    filename_bytes = filename_normalized.encode('utf-8')
    # Используем SHA-256 для получения стабильного хеша
    hash_object = hashlib.sha256(filename_bytes)
    hash_hex = hash_object.hexdigest()
    # Берем первые 8 символов хеша и конвертируем в int
    seed = int(hash_hex[:8], 16)

    return seed

# ============================================================================
# SCENE SETUP FUNCTIONS
# ============================================================================

def purge_scene():
    """Delete all objects and clear data."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for material in bpy.data.materials:
        bpy.data.materials.remove(material)
    for texture in bpy.data.textures:
        bpy.data.textures.remove(texture)
    for image in bpy.data.images:
        bpy.data.images.remove(image)

def make_emission_sphere(radius, color, strength):
    """Create hollow emission sphere for lighting."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0, 0, 0), segments=32, ring_count=16)
    sphere = bpy.context.active_object
    sphere.name = "EmissionSphere"

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode='OBJECT')

    mat = bpy.data.materials.new(name="EmissionMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = (*color, 1.0)
    emission.inputs['Strength'].default_value = strength

    output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])

    sphere.data.materials.append(mat)
    return sphere

def setup_world():
    """Set world background to black."""
    world = bpy.data.worlds.get('World')
    if not world:
        world = bpy.data.worlds.new('World')
        bpy.context.scene.world = world

    world.use_nodes = True
    bg_node = world.node_tree.nodes.get('Background')
    if bg_node:
        bg_node.inputs['Color'].default_value = (0, 0, 0, 1)
        bg_node.inputs['Strength'].default_value = 0.0

def import_obj_model(obj_path):
    """Import OBJ file."""
    mtl_path = obj_path.with_suffix('.mtl')
    has_mtl = mtl_path.exists()

    if has_mtl:
        log(f"  Found MTL: {mtl_path.name}")
    else:
        log(f"  No MTL found")

    bpy.ops.wm.obj_import(filepath=str(obj_path))
    imported_objects = [obj for obj in bpy.context.selected_objects]

    if not imported_objects:
        raise RuntimeError("No objects imported from OBJ file")

    log(f"  Imported {len(imported_objects)} objects")
    return imported_objects

def merge_to_single_object(objects):
    """Merge multiple objects into one."""
    if len(objects) == 1:
        return objects[0]

    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)

    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    merged = bpy.context.active_object
    merged.name = "MergedModel"

    log(f"  Merged {len(objects)} objects")
    return merged

def create_default_material():
    """Create default gray material."""
    mat = bpy.data.materials.new(name="DefaultMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    nodes.clear()

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.27, 0.28, 0.29, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.65
    bsdf.inputs['Metallic'].default_value = 0.2
    
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.5
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = 0.5

    output = nodes.new(type='ShaderNodeOutputMaterial')
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    return mat

def adjust_material_properties(model):
    """Adjust materials for TEXTURED rendering - preserve existing textures."""
    if not model.data.materials:
        log("  Creating default material")
        default_mat = create_default_material()
        model.data.materials.append(default_mat)
    else:
        for mat in model.data.materials:
            if not mat or not mat.use_nodes:
                continue

            nodes = mat.node_tree.nodes
            for node in nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    # КРИТИЧНО: НЕ трогаем Base Color если есть связь с текстурой!
                    if not node.inputs['Base Color'].links:
                        # Только если НЕТ текстуры, ставим дефолтный цвет
                        node.inputs['Base Color'].default_value = (0.7, 0.7, 0.7, 1.0)
                    
                    # Для текстурированных моделей оставляем разумные значения
                    # Не переопределяем Roughness/Metallic если они уже настроены из MTL
                    if not node.inputs['Roughness'].links:
                        node.inputs['Roughness'].default_value = 0.7  # было 0.9
                    if not node.inputs['Metallic'].links:
                        node.inputs['Metallic'].default_value = 0.0
                    
                    if 'Specular IOR Level' in node.inputs and not node.inputs['Specular IOR Level'].links:
                        node.inputs['Specular IOR Level'].default_value = 0.5
                    elif 'Specular' in node.inputs and not node.inputs['Specular'].links:
                        node.inputs['Specular'].default_value = 0.5

        log(f"  Adjusted {len(model.data.materials)} materials (texture-friendly)")

def verify_textures_loaded(model):
    """Verify that textures are properly loaded."""
    texture_count = 0
    for mat in model.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                texture_count += 1
                if node.image:
                    log(f"    Texture loaded: {node.image.name}")
                else:
                    log(f"    WARNING: Image node without image!")
    log(f"  Total textures: {texture_count}")

def set_origin_to_bbox_center(obj):
    """Set origin to bounding box center."""
    bpy.context.view_layer.objects.active = obj
    # bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME', center='BOUNDS')
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

def scale_to_bbox(obj, max_width, max_depth, max_height):
    """Scale object to fit bounding box."""
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    min_x = min(c.x for c in bbox_corners)
    max_x = max(c.x for c in bbox_corners)
    min_y = min(c.y for c in bbox_corners)
    max_y = max(c.y for c in bbox_corners)
    min_z = min(c.z for c in bbox_corners)
    max_z = max(c.z for c in bbox_corners)

    current_width = max_x - min_x
    current_depth = max_y - min_y
    current_height = max_z - min_z

    scale_x = max_width / current_width if current_width > 0 else 1.0
    scale_y = max_depth / current_depth if current_depth > 0 else 1.0
    scale_z = max_height / current_height if current_height > 0 else 1.0

    scale_factor = min(scale_x, scale_y, scale_z)
    obj.scale *= scale_factor

    log(f"  Scaled: {scale_factor:.4f}x")
'''
def place_camera(distance, h_eye, fov_degrees=60):
    """Create and position camera."""
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    camera.name = "Camera"

    camera.location = (0, -distance, h_eye + 0.7)

    target = Vector((0, 0, h_eye))
    direction = target - camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()

    camera.data.lens_unit = 'FOV'
    camera.data.angle = math.radians(fov_degrees)
    bpy.context.scene.camera = camera
    return camera
'''

# где-то в конфигурации
CAMERA_Z_OFFSET = 0.7  # было зашито 0.7

def place_camera(distance, h_eye, fov_degrees=60, z_offset=CAMERA_Z_OFFSET):
    """Create and position camera."""
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    camera.name = "Camera"

    # было: camera.location = (0, -distance, h_eye + 0.7)
    camera.location = (0, -distance, h_eye + z_offset)

    target = Vector((0, 0, h_eye))
    direction = target - camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()

    camera.data.lens_unit = 'FOV'
    camera.data.angle = math.radians(fov_degrees)

    # важно: сброс любых прежних сдвигов
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.0

    bpy.context.scene.camera = camera
    return camera

'''
def center_object_in_frame(cam, obj, center_x=False, center_y=True):
    """
    Ставит bbox модели по центру кадра за счёт camera.data.shift_[x|y].
    Работает при любом наклоне камеры (в т.ч. «сверху вниз»).
    """
    import math
    from mathutils import Vector

    # мир -> камера
    M = cam.matrix_world.inverted() @ obj.matrix_world
    corners = [M @ Vector(c) for c in obj.bound_box]

    # вертикальный FOV даёт корректную нормировку по высоте при 16:9/Auto
    angle_y = cam.data.angle_y

    ys = []
    xs = []
    for c in corners:
        # точки перед камерой имеют c.z < 0 (камера смотрит вдоль -Z)
        if c.z < -1e-6:
            # NDC-координаты по высоте/ширине
            ys.append( (c.y / -c.z) / math.tan(angle_y * 0.5) )
            # для X используем горизонтальный угол
            xs.append( (c.x / -c.z) / math.tan(cam.data.angle_x * 0.5) )

    if center_y and ys:
        center_ndc_y = 0.5 * (max(ys) + min(ys))
        # сдвиг направлен «в противоположную сторону» центра bbox
        cam.data.shift_y = -center_ndc_y

    if center_x and xs:
        center_ndc_x = 0.5 * (max(xs) + min(xs))
        cam.data.shift_x = -center_ndc_x
'''




def animate_yaw(obj, fps, duration_seconds, deg_per_second, seed, model_name):
    '''
    # Генерируем seed из имени модели, если не задан явно
    if seed is None and model_name is not None:
        seed = generate_seed_from_filename(model_name)
        log(f"  Generated seed from filename: {seed}")
    '''
    if seed is not None:
        random.seed(seed)
    '''
    start_angle_deg = random.uniform(0, 360)
    log(f"  Start angle: {start_angle_deg:.2f}°")

    yaw0 = random.uniform(0, 2 * math.pi)
    '''
    start_angle_deg = 0.0
    yaw0 = 0.0
    log(f"  Start angle: {start_angle_deg:.2f}°")
    omega = math.radians(deg_per_second)
    end_frame = int(fps * duration_seconds)

    obj.rotation_mode = 'XYZ'
    bpy.context.scene.frame_set(1)
    obj.rotation_euler.z = yaw0
    obj.keyframe_insert(data_path="rotation_euler", index=2, frame=1)

    bpy.context.scene.frame_set(end_frame)
    obj.rotation_euler.z = yaw0 + omega * duration_seconds
    obj.keyframe_insert(data_path="rotation_euler", index=2, frame=end_frame)

    if obj.animation_data and obj.animation_data.action:
        for fcurve in obj.animation_data.action.fcurves:
            if fcurve.data_path == "rotation_euler" and fcurve.array_index == 2:
                for kf in fcurve.keyframe_points:
                    kf.interpolation = 'LINEAR'

    return seed, yaw0 # изначальный угол и сид

# ============================================================================
# MVP LOGGING FUNCTIONS
# ============================================================================

def extract_static_mvp_data(camera, model, model_name, seed, start_angle_rad):
    """
    Извлекает статичные параметры сцены (сохраняются один раз для всего видео).
    
    Args:
        camera: Blender camera object
        model: 3D model object
        model_name: Name of the model
        seed: Random seed used
        start_angle_rad: Initial rotation angle in radians
    
    Returns:
        dict: Complete MVP data structure
    """
    import numpy as np
    
    log("  Extracting MVP static data...")

    # Текущая сцена
    scene = bpy.context.scene

    # Color Management
    view_settings = scene.view_settings
    display_settings = scene.display_settings

    # World (фон)
    world = scene.world
    bg_color = None
    bg_strength = None
    if world and world.use_nodes and world.node_tree:
        bg_node = world.node_tree.nodes.get('Background')
        if bg_node:
            # RGBA цвет фона
            bg_color = [float(x) for x in bg_node.inputs['Color'].default_value]
            bg_strength = float(bg_node.inputs['Strength'].default_value)

    
    # Получаем матрицы камеры
    cam_matrix_world = np.array(camera.matrix_world)
    view_matrix = np.linalg.inv(cam_matrix_world)
    
    # Получаем Projection matrix
    render = bpy.context.scene.render
    aspect_ratio = render.resolution_x / render.resolution_y
    
    # Вычисляем projection matrix вручную из FOV
    fov_rad = camera.data.angle
    f = 1.0 / math.tan(fov_rad / 2.0)
    near = camera.data.clip_start
    far = camera.data.clip_end
    
    # Perspective projection matrix (OpenGL style)
    projection_matrix = np.array([
        [f / aspect_ratio, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, -(far + near) / (far - near), -(2 * far * near) / (far - near)],
        [0, 0, -1, 0]
    ])
    
    static_data = {
        "model_name": model_name,
        "file_version": "1.0",
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        
        "video_info": {
            "fps": FPS,
            "duration_seconds": DURATION_SECONDS,
            "total_frames": int(FPS * DURATION_SECONDS),
            "resolution_width": RESOLUTION_X,
            "resolution_height": RESOLUTION_Y,
            "aspect_ratio": RESOLUTION_X / RESOLUTION_Y
        },
        

        # общие настройки рендера 
        "render_settings": {
            "engine": scene.render.engine,
            "device": scene.cycles.device,
            "samples": SAMPLES,
            "use_denoising": USE_DENOISING,
            "use_persistent_data": USE_PERSISTENT_DATA,
            "threads_mode": scene.render.threads_mode,
            "threads": scene.render.threads,
            "fps": FPS,
            "duration_seconds": DURATION_SECONDS,
            "deg_per_second": DEG_PER_SECOND,
        },

        # color management 
        "color_management": {
            # фактические значения из сцены
            "display_device": display_settings.display_device,
            "view_transform_scene": view_settings.view_transform,
            "look_scene": view_settings.look,
            "exposure_scene": float(view_settings.exposure),
            "gamma_scene": float(view_settings.gamma),

            # значения параметров скрипта (на случай, если их меняешь константами)
            "view_transform_param": VIEW_TRANSFORM,
            "exposure_param": float(EXPOSURE),
        },

        # освещение 
        "lighting": {
            # параметры, с которыми создаётся сфера
            "emission_color_param": list(EMISSION_COLOR),
            "emission_strength_param": float(EMISSION_STRENGTH),
            "rim_light_strength_param": float(RIM_LIGHT_STRENGTH),

            # состояние world-фона
            "world_background_color": bg_color,
            "world_background_strength": bg_strength,
        },


        "camera_static": {
            "location": [float(x) for x in camera.location],
            "rotation_euler_radians": [float(x) for x in camera.rotation_euler],
            "rotation_euler_degrees": [math.degrees(float(x)) for x in camera.rotation_euler],
            "fov_radians": float(camera.data.angle),
            "fov_degrees": math.degrees(camera.data.angle),
            "lens_mm": float(camera.data.lens),
            "sensor_width_mm": float(camera.data.sensor_width),
            "sensor_height_mm": float(camera.data.sensor_height),
            "clip_start": float(camera.data.clip_start),
            "clip_end": float(camera.data.clip_end),
            "view_matrix": view_matrix.tolist(),
            "projection_matrix": projection_matrix.tolist()
        },
        
        "model_static": {
            "location": [float(x) for x in model.location],
            "scale": [float(x) for x in model.scale],
            "bbox_max_dimensions": {
                "width": BBOX_MAX_WIDTH,
                "depth": BBOX_MAX_DEPTH,
                "height": BBOX_MAX_HEIGHT
            }
        },
        
        "animation": {
            # "seed": int(seed),
            "start_angle_radians": float(start_angle_rad),
            "start_angle_degrees": float(math.degrees(start_angle_rad)),
            "rotation_speed_deg_per_sec": float(DEG_PER_SECOND),
            "rotation_speed_rad_per_sec": float(math.radians(DEG_PER_SECOND)),
            "rotation_axis": "Z",
            "rotation_direction": "counter_clockwise"
        },
        
        "frames": []
    }
    
    log(f"  Start angle: {math.degrees(start_angle_rad):.2f}°")
    return static_data


def log_frame_mvp(mvp_data, frame_number, model):
    """
    Добавляет данные для одного кадра в структуру MVP.
    
    Args:
        mvp_data: Dictionary with MVP data
        frame_number: Current frame number
        model: 3D model object
    """
    frame_data = {
        "frame": frame_number,
        "timestamp": (frame_number - 1) / FPS,
        "rotation_z_radians": float(model.rotation_euler.z),
        "rotation_z_degrees": float(math.degrees(model.rotation_euler.z))
    }
    
    mvp_data["frames"].append(frame_data)


def save_mvp_data(mvp_data, model_name):
    """
    Сохраняет MVP данные в JSON файл.
    
    Args:
        mvp_data: Complete MVP data structure
        model_name: Name of the model
    
    Returns:
        Path: Path to saved JSON file
    """
    import json
    
    # Создаём директорию для MVP логов
    mvp_log_dir = LOG_DIR / "mvp_data"
    mvp_log_dir.mkdir(parents=True, exist_ok=True)
    
    # Имя файла: MeshMamba_non_log_{model_name}_mvp.json
    json_filename = f"MeshMamba_rgb_texture_{model_name}.json"
    json_path = mvp_log_dir / json_filename
    
    # Сохраняем с отступами для читаемости
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(mvp_data, f, indent=2, ensure_ascii=False)
    
    log(f"  MVP data saved: {json_path}")
    log(f"  Total frames logged: {len(mvp_data['frames'])}")
    
    return json_path

# конфигурация рендера

def configure_render(model_name, output_dir):
    """Configure render settings - GPU ONLY."""
    scene = bpy.context.scene
    
    # CRITICAL: Verify GPU before configuring
    verify_gpu_before_render()

    # Frame settings
    scene.frame_start = 1
    scene.frame_end = int(FPS * DURATION_SECONDS)
    scene.render.fps = FPS
    scene.render.fps_base = 1.0

    # Resolution
    scene.render.resolution_x = RESOLUTION_X
    scene.render.resolution_y = RESOLUTION_Y
    scene.render.resolution_percentage = 100
    scene.render.filter_size = 1.5  

    # CRITICAL: Force Cycles and GPU
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    
    # Limit CPU threads
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 4
    
    # Samples and denoising
    scene.cycles.samples = SAMPLES
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = USE_DENOISING
    bpy.context.view_layer.cycles.use_denoising = USE_DENOISING
    
    # Зафиксировать шумовой паттерн между кадрами
    if hasattr(scene.cycles, "use_animated_seed"):
        scene.cycles.use_animated_seed = False  # один и тот же seed на всех кадрах
        scene.cycles.seed = 0                   # можешь поставить любое фиксированное целое

    
    # Persistent data for GPU
    scene.render.use_persistent_data = True

    # Use OPTIX denoiser if available
    if USE_DENOISING:
        try:
            scene.cycles.denoiser = 'OPTIX'
        except:
            scene.cycles.denoiser = 'OPENIMAGEDENOISE'

    #
    # Настройки Color Management для реалистичных цветов
    '''
    scene.view_settings.view_transform = 'Filmic'  # или 'Standard' для более ярких цветов
    scene.view_settings.look = 'None'  # Без дополнительной обработки
    scene.view_settings.exposure = 0.0  # Можно уменьшить до -0.5 или -1.0 если всё равно яркое
    scene.view_settings.gamma = 1.0
    '''
    '''
    # Color Management: нейтральный вывод текстур
    # scene.display_settings.display_device = 'sRGB'      # стандартный монитор
    scene.view_settings.view_transform = VIEW_TRANSFORM # теперь 'Standard'
    scene.view_settings.look = 'None'                   # без доп. эффектов
    scene.view_settings.exposure = EXPOSURE             # 0.0
    scene.view_settings.gamma = 1.0
    '''
    scene.view_settings.look = 'None' 
    scene.view_settings.exposure = EXPOSURE  
    scene.view_settings.gamma = 1.0
    scene.view_settings.view_transform = VIEW_TRANSFORM
    # scene.display_settings.display_device = 'sRGB'
    #

    # Optimization settings
    scene.cycles.sample_clamp_indirect = 2.0
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 1
    #scene.cycles.transmission_bounces = 6
    scene.cycles.transmission_bounces = 0
    scene.cycles.volume_bounces = 0
    scene.cycles.transparent_max_bounces = 6
    
    # GPU tile size
    scene.cycles.tile_size = 2048

    # Output settings
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"MeshMamba_rgb_texture_{model_name}.mp4"

    scene.render.filepath = str(video_path)
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    #scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.ffmpeg.ffmpeg_preset = 'BEST'
    scene.render.ffmpeg.audio_codec = 'NONE'
    scene.render.ffmpeg.gopsize = FPS

    # параметризация освещения
    # scene.view_settings.view_transform = VIEW_TRANSFORM
    scene.view_settings.exposure = EXPOSURE

    log(f"  Output: {video_path}")
    
    # FINAL GPU CHECK
    if scene.cycles.device != 'GPU':
        log("CRITICAL: GPU lost, aborting!")
        sys.exit(1)
    
    return video_path

def render_animation():
    """Render animation - GPU ONLY."""
    # Final GPU verification
    verify_gpu_before_render()
    
    log("  Starting GPU render...")
    log(f"  Device: {bpy.context.scene.cycles.device}")
    log(f"  Threads: {bpy.context.scene.render.threads}")
    
    bpy.ops.render.render(animation=True)
    log("  Render complete!")

# ============================================================================
# MODEL PROCESSING
# ============================================================================
'''
def find_obj_file(model_dir):
    """Find .obj file in directory."""
    obj_files = list(model_dir.glob("*.obj"))
    return obj_files[0] if obj_files else None
'''

def find_obj_file(model_dir):
    candidates = [f for f in model_dir.iterdir() if f.is_file() and f.suffix.lower() == ".obj"]
    return candidates[0] if candidates else None


def process_single_model(obj_path, model_name):
    """Process single model with MVP logging."""
    log(f"\n{'='*80}")
    log(f"Processing: {model_name}")
    log(f"File: {obj_path}")
    log(f"{'='*80}")

    verify_gpu_before_render()

    purge_scene()
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.length_unit = 'METERS'
    setup_world()

    make_emission_sphere(SPHERE_RADIUS, EMISSION_COLOR, EMISSION_STRENGTH)

    imported_objects = import_obj_model(obj_path)
    model = merge_to_single_object(imported_objects)
    adjust_material_properties(model)
    verify_textures_loaded(model) 
    set_origin_to_bbox_center(model)
    scale_to_bbox(model, BBOX_MAX_WIDTH, BBOX_MAX_DEPTH, BBOX_MAX_HEIGHT)

    model.location = (0, 0, H_EYE)

    # Размещаем камеру
    camera = place_camera(CAMERA_DISTANCE, H_EYE)

    # Анимируем с получением seed и начального угла
    log("  Setting up animation with reproducible seed...")
    seed, start_angle_rad = animate_yaw(
        model, 
        FPS, 
        DURATION_SECONDS, 
        DEG_PER_SECOND, 
        seed=SEED,  # None - будет сгенерирован автоматически
        model_name=model_name
    )

    # ==================== MVP LOGGING ====================
    log("  Collecting MVP data for all frames...")
    
    # Извлекаем статичные данные
    mvp_data = extract_static_mvp_data(camera, model, model_name, seed, start_angle_rad)
    
    # Логируем данные для каждого кадра
    total_frames = int(FPS * DURATION_SECONDS)
    for frame in range(1, total_frames + 1):
        bpy.context.scene.frame_set(frame)
        log_frame_mvp(mvp_data, frame, model)
        
        # Прогресс каждые 50 кадров
        if frame % 50 == 0:
            log(f"    Logged frame {frame}/{total_frames}")
    
    # Сохраняем в JSON файл
    mvp_json_path = save_mvp_data(mvp_data, model_name)
    log(f"  MVP logging complete!")
    # ====================================================

    # Render
    video_path = configure_render(model_name, OUTPUT_DIR)
    render_animation()

    return video_path

def find_all_models():
    """Find all model folders."""
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Input directory not found: {INPUT_DIR}")

    model_folders = [d for d in INPUT_DIR.iterdir() if d.is_dir()]
    log(f"Found {len(model_folders)} model folders")
    return sorted(model_folders)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution."""
    try:
        init_logging()

        # Check CUDA_VISIBLE_DEVICES
        cuda_devices = os.environ.get('CUDA_VISIBLE_DEVICES', 'Not set')
        if cuda_devices != '1':
            log(f"WARNING: CUDA_VISIBLE_DEVICES={cuda_devices}, expected '3'")

        # CRITICAL: Force GPU-only mode
        if not force_gpu_only():
            log("FATAL: Cannot enable GPU!")
            log("Exiting to prevent CPU overload")
            sys.exit(1)

        # Find all models
        model_folders = find_all_models()
        total_models = len(model_folders)

        if total_models == 0:
            log("No models found!")
            return

        log(f"\nStarting GPU-ONLY batch render of {total_models} models")
        log("CPU threads limited to 4 to prevent server overload")
        log("=" * 80)

        success_count = 0
        error_count = 0
        skipped_count = 0

        for idx, model_folder in enumerate(model_folders, 1):
            model_name = model_folder.name

            try:
                log_progress(idx, total_models, model_name, "Starting")

                obj_path = find_obj_file(model_folder)

                if not obj_path:
                    log_error(f"No .obj file in {model_folder}")
                    log_progress(idx, total_models, model_name, "SKIPPED - No OBJ")
                    skipped_count += 1
                    continue

                output_path = OUTPUT_DIR / f"MeshMamba_rgb_texture_{model_name}.mp4"
                if output_path.exists():
                    log(f"  Already exists: {output_path}")
                    log_progress(idx, total_models, model_name, "SKIPPED - Exists")
                    skipped_count += 1
                    continue

                video_path = process_single_model(obj_path, model_name)
                log_progress(idx, total_models, model_name, "SUCCESS")
                success_count += 1

            except Exception as e:
                log_error(f"Failed: {model_name}", e)
                log_progress(idx, total_models, model_name, f"ERROR: {str(e)}")
                error_count += 1
                continue

        # Summary
        log("\n" + "=" * 80)
        log("BATCH RENDER COMPLETE")
        log(f"Total: {total_models}")
        log(f"Success: {success_count}")
        log(f"Errors: {error_count}")
        log(f"Skipped: {skipped_count}")
        log(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log("=" * 80)

        close_logging()

    except Exception as e:
        log_error(f"CRITICAL ERROR: {str(e)}", e)
        close_logging()
        raise

if __name__ == "__main__":
    main()