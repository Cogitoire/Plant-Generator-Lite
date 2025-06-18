bl_info = {
    "name": "Plant Generator Lite",
    "author": "AI Assistant & Cogitoire",
    "version": (0, 2, 1), # バージョンを少し上げました
    "blender": (3, 0, 0), # Blender 3.0以上を推奨
    "location": "View3D > Sidebar > Plant Gen Tab",
    "description": "Generates plant-like structures: Vogel patterns and L-Systems with presets.",
    "warning": "This is a simplified version for demonstration.",
    "doc_url": "https://github.com/Cogitoire/Plant-Generator-Lite",
    "category": "Add Mesh",
}

import bpy
import bmesh # Blenderのメッシュ編集に非常に便利
import numpy as np
import math
from mathutils import Vector, Matrix, Quaternion # Blenderの数学ユーティリティ


# --- 新機能：L-Systemプリセットが変更されたときにパラメータを更新するコールバック関数 ---
def update_lsystem_preset(self, context):
    """L-Systemプリセットが変更されたときにパラメータを更新するコールバック関数"""
    
    if self.preset == 'RECIPE_1':
        self.axiom = "F"
        self.rules_input = "F:F[+F]F[-F]F"
        self.iterations = 3
        self.angle = 25.7
        self.add_leaves = False
        
    elif self.preset == 'RECIPE_2':
        self.axiom = "X"
        # カンマ区切りで複数のルールを記述
        self.rules_input = "X:F+[[X]-X]-F[-FX]+X, F:FF"
        self.iterations = 4
        self.angle = 25.0
        self.add_leaves = False

    elif self.preset == 'RECIPE_3':
        self.axiom = "F"
        self.rules_input = "F:F[-L][+L]F"
        self.iterations = 4
        self.angle = 30.0
        self.add_leaves = True # このレシピでは葉を有効にする

    # 'CUSTOM' が選択された場合は何もしない。ユーザーが自由に変更するため。


# --- 1. Property Groups (UIで使うパラメータ) ---
class VogelProperties(bpy.types.PropertyGroup):
    num_points: bpy.props.IntProperty(
        name="Points",
        description="Number of points (florets/seeds)",
        default=200, min=1, max=10000
    )
    scaling_factor_c: bpy.props.FloatProperty(
        name="Scale (c)",
        description="Scaling factor for the spiral",
        default=0.1, min=0.001, max=10.0
    )
    point_size: bpy.props.FloatProperty(
        name="Point Size",
        description="Size of the points (if represented by icospheres)",
        default=0.02, min=0.001, max=1.0
    )
    use_icospheres: bpy.props.BoolProperty(
        name="Use Icospheres for Points",
        description="Represent points as icospheres, otherwise use custom object or vertices",
        default=True
    )
    z_offset: bpy.props.FloatProperty(
        name="Z Offset",
        description="Optional Z offset for each point, can create curvature: z = z_factor * sqrt(n)",
        default=0.0, min=-1.0, max=1.0
    )
    z_factor_curvature: bpy.props.FloatProperty(
        name="Z Curvature",
        description="Factor for Z curvature based on radius (z = factor * radius^2)",
        default=0.0, min=-5.0, max=5.0
    )
    use_custom_instance_object: bpy.props.BoolProperty(
        name="Use Custom Object",
        description="Instance a custom object at each point instead of icospheres/vertices. Overrides 'Use Icospheres'.",
        default=False
    )
    instance_object: bpy.props.PointerProperty(
        name="Instance Object",
        description="Object to instance at each point",
        type=bpy.types.Object
    )
    instance_scale: bpy.props.FloatProperty(
        name="Instance Scale",
        description="Scale of the instanced object",
        default=0.1, min=0.001, max=10.0
    )
    # align_to_normal は leaf_orientation_mode に置き換えられました
    # align_to_normal: bpy.props.BoolProperty(
    #     name="Align to Normal/Center",
    #     description="Align instanced objects to face outwards from the center or along a calculated normal",
    #     default=True
    # )
    leaf_orientation_mode: bpy.props.EnumProperty(
        name="Leaf Orientation",
        description="How to orient instanced leaves. Assumes leaf model's +Y is forward, +Z is up.",
        items=[
            ('NORMAL', "Align to Point Normal", "Align leaf's Y-axis outwards from the point, Z-axis towards World Up"),
            ('UPWARD', "Upward (World Z)", "Align leaf's Y-axis to point upwards (World Z-axis)"),
        ],
        default='NORMAL',
    )
    leaf_upward_tilt_angle: bpy.props.FloatProperty(
        name="Upward Tilt (Normal Mode)",
        description="Angle to tilt leaves towards Z-up when 'Align to Point Normal' is active. 0°=Horizontal, 90°=Vertical.",
        default=0.0, min=0.0, max=90.0, subtype='ANGLE', unit='ROTATION'
    )

class LSystemProperties(bpy.types.PropertyGroup):
    # --- 新機能：L-Systemプリセット選択用のプロパティ ---
    preset: bpy.props.EnumProperty(
        name="Preset",
        description="Load a preset configuration for the L-System",
        items=[
            # (識別子, UI表示名, ツールチップ, アイコン, 番号)
            ('CUSTOM', "Custom", "Custom settings", 'MODIFIER', 0),
            ('RECIPE_1', "Simple Tree", "A simple branching tree", 'TRACKING_FORWARDS', 1),
            ('RECIPE_2', "Organic Plant", "An organic, asymmetric plant", 'SNAP_LEAF', 2),
            ('RECIPE_3', "Plant with Leaves", "A plant with leaves", 'OUTLINER_OB_GREASEPENCIL', 3),
        ],
        default='CUSTOM',
        update=update_lsystem_preset # 値が変更されたらこの関数を呼び出す
    )

    axiom: bpy.props.StringProperty(
        name="Axiom",
        description="Starting string for the L-System",
        default="F" # シンプルなものから
    )
    rules_input: bpy.props.StringProperty(
        name="Rules",
        description="L-System rules (e.g., 'F:F[+F]F[-F]F, X:...')",
        default="F:F[+F]F[-F]F"
    )
    iterations: bpy.props.IntProperty(
        name="Iterations",
        description="Number of times to apply rules",
        default=3, min=1, max=8 # 大きすぎると重くなる
    )
    angle: bpy.props.FloatProperty(
        name="Angle (°)",
        description="Default angle for + and - commands",
        default=25.7, min=0.0, max=360.0
    )
    length: bpy.props.FloatProperty(
        name="Length",
        description="Length of each 'F' segment",
        default=0.2, min=0.01, max=5.0
    )
    initial_direction: bpy.props.FloatVectorProperty(
        name="Initial Direction",
        description="Initial direction vector (e.g., Z-up)",
        default=(0.0, 0.0, 1.0), # (X, Y, Z)
        subtype='DIRECTION'
    )
    leaf_symbol: bpy.props.StringProperty(
        name="Leaf Symbol",
        description="Symbol in rules to represent a leaf (e.g., L)",
        default="L" # このシンボルが登場したら葉を配置
    )
    add_leaves: bpy.props.BoolProperty(
        name="Add Leaves",
        description="Generate leaves at specified symbol",
        default=False
    )
    leaf_object: bpy.props.PointerProperty(
        name="Leaf Object",
        description="Object to use as a leaf (optional, creates simple plane if None)",
        type=bpy.types.Object
    )
    leaf_scale: bpy.props.FloatProperty(
        name="Leaf Scale",
        description="Scale of the generated/instanced leaf",
        default=0.1, min=0.01, max=2.0
    )


# --- 2. Operators (実際の処理) ---

# Vogelのモデル生成オペレータ
class VOGEL_OT_Generate(bpy.types.Operator):
    bl_idname = "plant_gen.vogel_generate"
    bl_label = "Generate Vogel Pattern"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.vogel_props
        
        golden_angle_rad = math.pi * (3.0 - math.sqrt(5.0))
        
        generated_objects = [] # 生成されたオブジェクトを追跡

        # 頂点のみのメッシュを生成する場合の頂点リスト
        verts_only_list = []

        for n in range(props.num_points):
            theta = n * golden_angle_rad
            radius_xy = props.scaling_factor_c * math.sqrt(n)
            x = radius_xy * math.cos(theta)
            y = radius_xy * math.sin(theta)
            z_calc = props.z_offset * math.sqrt(n) + props.z_factor_curvature * (radius_xy**2)
            current_pos = Vector((x, y, z_calc))

            if props.use_custom_instance_object and props.instance_object:
                source_obj = props.instance_object
                
                new_obj = source_obj.copy()
                if source_obj.data:
                    new_obj.data = source_obj.data.copy()
                new_obj.animation_data_clear()
                context.collection.objects.link(new_obj)
                
                new_obj.location = current_pos
                new_obj.scale = (props.instance_scale, props.instance_scale, props.instance_scale)

                # --- 葉の向きを制御 ---
                new_obj.rotation_mode = 'QUATERNION'

                # Assumes leaf instance model has its "forward" along its local Y-axis,
                # and its "up" along its local Z-axis.

                # Default rotation to make the leaf's local Y-axis point along World +Z (upwards).
                # This is a 90-degree rotation around the World X-axis.
                rot_y_to_world_z = Quaternion((1.0, 0.0, 0.0), math.radians(90.0))

                if props.leaf_orientation_mode == 'UPWARD':
                    new_obj.rotation_quaternion = rot_y_to_world_z
                
                elif props.leaf_orientation_mode == 'NORMAL':
                    if radius_xy > 0.0001: # Not at the exact center
                        # Direction from center in XY plane (horizontal component of normal)
                        radial_dir_xy = Vector((x, y, 0.0)).normalized()
                        world_z_axis = Vector((0.0, 0.0, 1.0))
                        
                        # tilt_factor: 0 means leaf Y-axis aligns with radial_dir_xy (horizontal)
                        #              1 means leaf Y-axis aligns with world_z_axis (vertical)
                        tilt_factor = props.leaf_upward_tilt_angle / 90.0
                        
                        # Calculate the target direction for the leaf's local Y-axis
                        target_y_direction = radial_dir_xy.lerp(world_z_axis, tilt_factor).normalized()
                        
                        # Align leaf's local Y to target_y_direction, and local Z to World Z.
                        # to_track_quat('Y', 'Z') does this:
                        # - Rotates so local Y points along the vector it's called on (target_y_direction).
                        # - Rotates so local Z points along World Z as much as possible.
                        final_rotation = target_y_direction.to_track_quat('Y', 'Z')
                        new_obj.rotation_quaternion = final_rotation
                    else: # At the exact center
                        # For the center point, make the leaf's Y-axis point upwards.
                        new_obj.rotation_quaternion = rot_y_to_world_z
                
                # The original object's (instance_object) rotation is NOT applied here by default.
                # The generated rotation is considered absolute for the instance.
                # If you need to apply the source object's rotation as well, you could add:
                # new_obj.rotation_quaternion @= props.instance_object.rotation_euler.to_quaternion()
                generated_objects.append(new_obj)

            elif props.use_icospheres:
                ico_mesh = bpy.data.meshes.new(name="VogelPointSphere")
                bm = bmesh.new()
                bmesh.ops.create_icosphere(bm, subdivisions=2, radius=props.point_size)
                bm.to_mesh(ico_mesh)
                bm.free()
                
                ico_obj = bpy.data.objects.new("VogelPoint", ico_mesh)
                ico_obj.location = current_pos
                context.collection.objects.link(ico_obj)
                generated_objects.append(ico_obj)
            else:
                # 頂点のみを生成する場合は、ループの最後にまとめて処理
                verts_only_list.append(current_pos)

        # 頂点のみのメッシュ生成をループの外で実行
        if verts_only_list:
            mesh = bpy.data.meshes.new(name="VogelPatternVertices")
            mesh.from_pydata(verts_only_list, [], [])
            mesh.update()
            obj = bpy.data.objects.new("VogelPatternObject", mesh)
            context.collection.objects.link(obj)
            generated_objects.append(obj)

        if not generated_objects:
            self.report({'WARNING'}, "No objects were generated.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"{len(generated_objects)} elements generated for Vogel pattern.")
        return {'FINISHED'}

# L-システムの植物生成オペレータ
class LSYSTEM_OT_Generate(bpy.types.Operator):
    bl_idname = "plant_gen.lsystem_generate"
    bl_label = "Generate L-System Plant"
    bl_options = {'REGISTER', 'UNDO'}

    def apply_rules_lsystem(self, current_string, rules_dict):
        new_string = []
        for char in current_string:
            new_string.append(rules_dict.get(char, char))
        return "".join(new_string)

    def execute(self, context):
        props = context.scene.lsystem_props

        # --- 新機能：複数ルールに対応したパーサー ---
        rules_dict = {}
        # カンマ(,)で各ルール定義を分割
        rule_pairs = [r.strip() for r in props.rules_input.split(',') if r.strip()]

        if not rule_pairs:
            self.report({'ERROR'}, "Rules cannot be empty.")
            return {'CANCELLED'}

        for pair in rule_pairs:
            if ':' in pair:
                key, value = pair.split(':', 1)
                rules_dict[key.strip()] = value.strip()
            else:
                self.report({'ERROR'}, f"Rule '{pair}' format incorrect. Use 'Symbol:Replacement'.")
                return {'CANCELLED'}

        if not rules_dict:
            self.report({'ERROR'}, "No valid rules parsed.")
            return {'CANCELLED'}
        
        # L-システムの文字列を展開
        current_ls_string = props.axiom
        for _ in range(props.iterations):
            current_ls_string = self.apply_rules_lsystem(current_ls_string, rules_dict)

        bm = bmesh.new()

        position = Vector((0.0, 0.0, 0.0))
        heading_vec = Vector(props.initial_direction).normalized()
        
        if abs(heading_vec.dot(Vector((0,0,1)))) < 0.99:
            left_vec = heading_vec.cross(Vector((0,0,1))).normalized()
            up_vec = left_vec.cross(heading_vec).normalized()
        else:
            left_vec = heading_vec.cross(Vector((0,1,0))).normalized()
            up_vec = left_vec.cross(heading_vec).normalized()

        stack = []
        angle_rad = math.radians(props.angle)

        for command in current_ls_string:
            if command == "F" or command == "G":
                start_pos_vert = bm.verts.new(position.copy())
                position += heading_vec * props.length
                end_pos_vert = bm.verts.new(position.copy())
                if command == "F":
                    bm.edges.new((start_pos_vert, end_pos_vert))

            elif command == "+":
                rot_quat = Quaternion(up_vec, angle_rad)
                heading_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)
                
            elif command == "-":
                rot_quat = Quaternion(up_vec, -angle_rad)
                heading_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)

            elif command == "&":
                rot_quat = Quaternion(left_vec, angle_rad)
                heading_vec.rotate(rot_quat)
                up_vec.rotate(rot_quat)

            elif command == "^":
                rot_quat = Quaternion(left_vec, -angle_rad)
                heading_vec.rotate(rot_quat)
                up_vec.rotate(rot_quat)

            elif command == "\\":
                rot_quat = Quaternion(heading_vec, angle_rad)
                up_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)

            elif command == "/":
                rot_quat = Quaternion(heading_vec, -angle_rad)
                up_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)

            elif command == "[":
                stack.append({
                    'pos': position.copy(),
                    'H': heading_vec.copy(),
                    'U': up_vec.copy(),
                    'L': left_vec.copy(),
                })
            elif command == "]":
                if stack:
                    data = stack.pop()
                    position = data['pos']
                    heading_vec = data['H']
                    up_vec = data['U']
                    left_vec = data['L']
                else:
                    self.report({'WARNING'}, "L-System stack empty, unbalanced ']'")
            
            elif props.add_leaves and command == props.leaf_symbol:
                if props.leaf_object:
                    leaf_obj_instance = bpy.data.objects.new(name=f"Leaf_{props.leaf_object.name}", object_data=props.leaf_object.data.copy())
                    context.collection.objects.link(leaf_obj_instance)
                    leaf_obj_instance.location = position.copy()
                    
                    rot_matrix = Matrix((left_vec, heading_vec, up_vec)).transposed()
                    leaf_obj_instance.rotation_mode = 'QUATERNION'
                    leaf_obj_instance.rotation_quaternion = rot_matrix.to_quaternion()
                    leaf_obj_instance.scale = (props.leaf_scale, props.leaf_scale, props.leaf_scale)
                else:
                    leaf_bm = bmesh.new()
                    v1 = leaf_bm.verts.new((-0.5 * props.leaf_scale, 0, 0))
                    v2 = leaf_bm.verts.new(( 0.5 * props.leaf_scale, 0, 0))
                    v3 = leaf_bm.verts.new(( 0.5 * props.leaf_scale, 1.0 * props.leaf_scale, 0))
                    v4 = leaf_bm.verts.new((-0.5 * props.leaf_scale, 1.0 * props.leaf_scale, 0))
                    leaf_bm.faces.new((v1, v2, v3, v4))
                    
                    transform_matrix = Matrix.Translation(position) @ Matrix((left_vec, heading_vec, up_vec)).transposed().to_4x4()

                    temp_leaf_verts = []
                    for v_idx in leaf_bm.verts:
                        v_world = transform_matrix @ v_idx.co
                        temp_leaf_verts.append(bm.verts.new(v_world))
                    
                    if len(temp_leaf_verts) == 4:
                        try:
                            bm.faces.new(temp_leaf_verts)
                        except ValueError:
                            pass # Avoids error with degenerate faces if any
                    leaf_bm.free()

        if len(bm.verts) > 0:
            mesh_data = bpy.data.meshes.new("LSystemMesh")
            bm.to_mesh(mesh_data)
            bm.free()

            obj = bpy.data.objects.new("LSystemPlant", mesh_data)
            context.collection.objects.link(obj)
            self.report({'INFO'}, f"L-System plant generated with {len(current_ls_string)} commands.")
        else:
            bm.free()
            self.report({'WARNING'}, "L-System resulted in no geometry.")

        return {'FINISHED'}


# --- 3. Panels (UIの定義) ---
class PLANTGEN_PT_MainPanel(bpy.types.Panel):
    bl_label = "Plant Gen Lite"
    bl_idname = "PLANTGEN_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Plant Gen'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Vogel's Model Section
        box_vogel = layout.box()
        box_vogel.label(text="Vogel Phyllotaxis", icon='OUTLINER_OB_POINTCLOUD')
        v_props = scene.vogel_props
        box_vogel.prop(v_props, "num_points")
        box_vogel.prop(v_props, "scaling_factor_c")

        box_vogel.prop(v_props, "use_custom_instance_object")

        if v_props.use_custom_instance_object:
            box_vogel.prop(v_props, "instance_object")
            box_vogel.prop(v_props, "instance_scale")
            box_vogel.prop(v_props, "leaf_orientation_mode")
            if v_props.leaf_orientation_mode == 'NORMAL':
                box_vogel.prop(v_props, "leaf_upward_tilt_angle")
        else:
            box_vogel.prop(v_props, "use_icospheres")
            if v_props.use_icospheres:
                box_vogel.prop(v_props, "point_size")

        box_vogel.prop(v_props, "z_offset")
        box_vogel.prop(v_props, "z_factor_curvature")
        box_vogel.operator(VOGEL_OT_Generate.bl_idname, text="Generate Vogel Pattern")
    
        # L-System Section
        box_lsystem = layout.box()
        box_lsystem.label(text="L-System Plant", icon='MOD_TREE')
        l_props = scene.lsystem_props
        
        # --- 新機能：プリセット選択UI ---
        row = box_lsystem.row()
        row.prop(l_props, "preset", expand=True)

        box_lsystem.prop(l_props, "axiom")
        box_lsystem.prop(l_props, "rules_input")
        box_lsystem.prop(l_props, "iterations")
        box_lsystem.prop(l_props, "angle")
        box_lsystem.prop(l_props, "length")
        box_lsystem.prop(l_props, "initial_direction")
        
        row = box_lsystem.row()
        row.prop(l_props, "add_leaves")
        if l_props.add_leaves:
            row.prop(l_props, "leaf_symbol")
        
        if l_props.add_leaves:
            box_lsystem.prop(l_props, "leaf_object")
            box_lsystem.prop(l_props, "leaf_scale")

        box_lsystem.operator(LSYSTEM_OT_Generate.bl_idname, text="Generate L-System Plant")


# --- 4. Register/Unregister ---
classes = (
    VogelProperties,
    LSystemProperties,
    VOGEL_OT_Generate,
    LSYSTEM_OT_Generate,
    PLANTGEN_PT_MainPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vogel_props = bpy.props.PointerProperty(type=VogelProperties)
    bpy.types.Scene.lsystem_props = bpy.props.PointerProperty(type=LSystemProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.vogel_props
    del bpy.types.Scene.lsystem_props

if __name__ == "__main__":
    # This part is for testing in Blender's text editor
    # If you run this script directly, it will try to unregister first,
    # then register, to allow for quick reloading.
    try:
        unregister()
    except Exception as e:
        print(f"Error during unregister (normal if first run): {e}")
        pass
    register()

    # Example usage (optional, for testing)
    # bpy.ops.plant_gen.vogel_generate()
    # bpy.ops.plant_gen.lsystem_generate()
