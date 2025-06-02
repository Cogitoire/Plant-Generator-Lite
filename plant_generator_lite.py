bl_info = {
    "name": "Plant Generator Lite",
    "author": "AI Assistant & Cogitoire",
    "version": (0, 1, 0),
    "blender": (3, 0, 0), # Blender 3.0以上を推奨
    "location": "View3D > Sidebar > Plant Gen Tab",
    "description": "Generates plant-like structures: Vogel patterns and L-Systems.",
    "warning": "This is a simplified version for demonstration.",
    "doc_url": "https://github.com/Cogitoire/Plant-Generator-Lite",
    "category": "Add Mesh",
}

import bpy
import bmesh # Blenderのメッシュ編集に非常に便利
import numpy as np
import math
from mathutils import Vector, Matrix, Quaternion # Blenderの数学ユーティリティ

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
    # --- ↓↓↓ 正しい位置に移動させるプロパティ ↓↓↓ ---
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
    align_to_normal: bpy.props.BoolProperty(
        name="Align to Normal/Center",
        description="Align instanced objects to face outwards from the center or along a calculated normal",
        default=True
    )

class LSystemProperties(bpy.types.PropertyGroup):
    axiom: bpy.props.StringProperty(
        name="Axiom",
        description="Starting string for the L-System",
        default="F" # シンプルなものから
    )
    rules_input: bpy.props.StringProperty(
        name="Rules",
        description="L-System rules (e.g., F:F[+F]F[-F]F )",
        default="F:F[+F]F[-F]F" # カンマ区切りなどで複数ルール対応も可能だが、ここでは1ルール想定
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
        
        generated_objects = [] # 生成されたオブジェクトを追跡（後で選択したり親にしたりする場合）

        for n in range(props.num_points):
            theta = n * golden_angle_rad
            radius_xy = props.scaling_factor_c * math.sqrt(n)
            x = radius_xy * math.cos(theta)
            y = radius_xy * math.sin(theta)
            # Z座標に変化を加える
            z_calc = props.z_offset * math.sqrt(n) + props.z_factor_curvature * (radius_xy**2)
            current_pos = Vector((x, y, z_calc))

            if props.use_custom_instance_object and props.instance_object:
                # --- カスタムオブジェクトをインスタンス化 ---
                source_obj = props.instance_object
                
                # オブジェクトを複製 (リンク複製ではなく、独立したオブジェクトとして)
                # パフォーマンスを考慮するなら、インスタンスコレクションやリンク複製も検討
                new_obj = source_obj.copy()
                if source_obj.data: # メッシュデータなどがある場合
                    new_obj.data = source_obj.data.copy() # メッシュデータもコピー
                new_obj.animation_data_clear() # アニメーションデータはクリア
                context.collection.objects.link(new_obj)
                
                new_obj.location = current_pos
                new_obj.scale = (props.instance_scale, props.instance_scale, props.instance_scale)

                if props.align_to_normal:
                    # --- 向きの調整 ---
                    # 中心(0,0,z_calc)から現在の点への方向ベクトルを計算
                    # 簡単な方法: Y軸を外側に向け、Z軸をワールドのZ軸に近づける
                    if radius_xy > 0.0001: # 中心点は向きが定義しにくい
                        dir_to_point = Vector((x, y, 0)).normalized() # XY平面での中心からの方向
                        # Y軸がこの方向を向くような回転クォータニオン
                        # Z軸はグローバルZを維持しようとする
                        quat_rotation = dir_to_point.to_track_quat('Y', 'Z')
                        new_obj.rotation_mode = 'QUATERNION'
                        new_obj.rotation_quaternion = quat_rotation
                    else: # 中心点
                        new_obj.rotation_euler = (0,0,0) # デフォルトの向き
                else:
                    new_obj.rotation_euler = source_obj.rotation_euler # 元オブジェクトの向きを維持

                generated_objects.append(new_obj)

            elif props.use_icospheres: # use_custom_instance_objectがFalseの場合
                # --- 各点にICO球を配置 ---
                # (既存のICO球生成コードをここに移動)
                # bpy.ops.object.primitive_add だとアクティブオブジェクトに影響するので注意
                # bmeshでICO球を作るか、bpy.data.objects.newで作成する方が望ましい
                
                ico_mesh = bpy.data.meshes.new(name="VogelPointSphere")
                bm = bmesh.new()
                bmesh.ops.create_icosphere(bm, subdivisions=2, radius=props.point_size) # subdivisionsを調整可能にしても良い
                bm.to_mesh(ico_mesh)
                bm.free()
                
                ico_obj = bpy.data.objects.new("VogelPoint", ico_mesh)
                ico_obj.location = current_pos
                context.collection.objects.link(ico_obj)
                generated_objects.append(ico_obj)

            # (use_custom_instance_objectもuse_icospheresもFalseの場合は頂点のみのメッシュを生成)
            # この部分は後述

        # --- 頂点のみのメッシュ生成 (オプション) ---
        if not props.use_custom_instance_object and not props.use_icospheres:
            verts = []
            for n in range(props.num_points):
                theta = n * golden_angle_rad
                radius_xy = props.scaling_factor_c * math.sqrt(n)
                x = radius_xy * math.cos(theta)
                y = radius_xy * math.sin(theta)
                z_calc = props.z_offset * math.sqrt(n) + props.z_factor_curvature * (radius_xy**2)
                verts.append(Vector((x, y, z_calc)))

            if verts:
                mesh = bpy.data.meshes.new(name="VogelPatternVertices")
                mesh.from_pydata(verts, [], [])
                mesh.update()
                obj = bpy.data.objects.new("VogelPatternObject", mesh)
                context.collection.objects.link(obj)
                generated_objects.append(obj) # これも生成物リストに追加
            else:
                 self.report({'WARNING'}, "No points generated for vertex-only mode.")
                 return {'CANCELLED'}


        if not generated_objects:
            self.report({'WARNING'}, "No objects were generated.")
            return {'CANCELLED'}

        # (オプション) 全ての生成されたオブジェクトを選択状態にする
        # bpy.ops.object.select_all(action='DESELECT')
        # for obj in generated_objects:
        # obj.select_set(True)
        # if generated_objects:
        # context.view_layer.objects.active = generated_objects[0]

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

        # ルールのパース (簡易版: "F:F[+F]")
        # より複雑なルールセットには、より堅牢なパーサーが必要
        rules_dict = {}
        if ':' in props.rules_input:
            key, value = props.rules_input.split(':', 1)
            rules_dict[key.strip()] = value.strip()
        else:
            self.report({'ERROR'}, "Rule format incorrect. Use 'Symbol:Replacement'.")
            return {'CANCELLED'}

        # L-システムの文字列を展開
        current_ls_string = props.axiom
        for _ in range(props.iterations):
            current_ls_string = self.apply_rules_lsystem(current_ls_string, rules_dict)

        # bmeshを使ってメッシュを構築
        bm = bmesh.new()

        # タートルの状態 (位置、向き、スタック)
        # 向きはクォータニオンまたは回転行列で管理
        position = Vector((0.0, 0.0, 0.0))
        
        # 初期向きをクォータニオンで設定
        # props.initial_direction は Vector。これを回転に変換
        # Z軸が(0,0,1)の場合、回転なし。Y軸が(0,1,0)ならXを90度回転など。
        # ここでは単純にZ軸を向いているベクトルからの回転として扱う
        # BlenderのデフォルトオブジェクトはZが上なので、initial_directionが(0,0,1)なら回転なしでよい。
        # heading_quat = Vector(props.initial_direction).to_track_quat('Z', 'Y') # 'Z'が向く方向, 'Y'がロール軸
        # より直接的に、初期のH, U, Lベクトルを定義する
        
        heading_vec = Vector(props.initial_direction).normalized()
        # up_vecとleft_vecをheading_vecから計算 (Gram-Schmidt法などで直交化が必要な場合も)
        # 簡単のため、グローバルZがUPでない限り、up_vecの初期値を調整する必要がある
        if abs(heading_vec.dot(Vector((0,0,1)))) < 0.99: # headingがほぼZ軸でないなら
            left_vec = heading_vec.cross(Vector((0,0,1))).normalized()
            up_vec = left_vec.cross(heading_vec).normalized()
        else: # headingがほぼZ軸（上か下）なら
            left_vec = heading_vec.cross(Vector((0,1,0))).normalized() # Y軸を仮の横方向とする
            up_vec = left_vec.cross(heading_vec).normalized()


        stack = []
        
        # 最初の頂点
        # last_bm_vert = bm.verts.new(position) # 線を描かない場合は不要かも

        angle_rad = math.radians(props.angle)

        # 葉を配置するためのオブジェクトリスト
        leaf_meshes_to_join = []


        for command in current_ls_string:
            if command == "F" or command == "G": # F: 線を描いて前進, G: 線を描かずに前進(として追加)
                start_pos_vert = bm.verts.new(position.copy()) # セグメント開始点

                position += heading_vec * props.length
                
                end_pos_vert = bm.verts.new(position.copy())   # セグメント終了点
                if command == "F":
                    bm.edges.new((start_pos_vert, end_pos_vert))
                # last_bm_vert = end_pos_vert # 次のセグメントのために更新

            elif command == "+": # 左回転 (Upベクトル周り)
                rot_quat = Quaternion(up_vec, angle_rad)
                heading_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)
                
            elif command == "-": # 右回転 (Upベクトル周り)
                rot_quat = Quaternion(up_vec, -angle_rad)
                heading_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)

            elif command == "&": # ピッチダウン (Leftベクトル周り)
                rot_quat = Quaternion(left_vec, angle_rad)
                heading_vec.rotate(rot_quat)
                up_vec.rotate(rot_quat)

            elif command == "^": # ピッチアップ (Leftベクトル周り)
                rot_quat = Quaternion(left_vec, -angle_rad)
                heading_vec.rotate(rot_quat)
                up_vec.rotate(rot_quat)

            elif command == "\\": # ロール左 (Headingベクトル周り)
                rot_quat = Quaternion(heading_vec, angle_rad)
                up_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)

            elif command == "/": # ロール右 (Headingベクトル周り)
                rot_quat = Quaternion(heading_vec, -angle_rad)
                up_vec.rotate(rot_quat)
                left_vec.rotate(rot_quat)

            elif command == "[":
                stack.append({
                    'pos': position.copy(),
                    'H': heading_vec.copy(),
                    'U': up_vec.copy(),
                    'L': left_vec.copy(),
                    # 'vert': last_bm_vert # 分岐点に戻るために頂点も保存する場合
                })
            elif command == "]":
                if stack:
                    data = stack.pop()
                    position = data['pos']
                    heading_vec = data['H']
                    up_vec = data['U']
                    left_vec = data['L']
                    # last_bm_vert = data['vert'] # 分岐点に戻る
                    # 分岐後は新しい頂点から開始するので、bm.verts.new(position)で新しい開始点を作る
                else:
                    self.report({'WARNING'}, "L-System stack empty, unbalanced ']'")
            
            elif props.add_leaves and command == props.leaf_symbol:
                if props.leaf_object:
                    # ユーザー指定のオブジェクトをインスタンス化
                    leaf_obj_instance = bpy.data.objects.new(name=f"Leaf_{props.leaf_object.name}", object_data=props.leaf_object.data.copy()) # メッシュをコピー
                    context.collection.objects.link(leaf_obj_instance)
                    leaf_obj_instance.location = position.copy()
                    # 向きをタートルの向きに合わせる (HがY軸、UがZ軸になるように)
                    # heading_vec (Ylocal), up_vec (Zlocal), left_vec (Xlocal)
                    # Blenderのクォータニオンは (w, x, y, z)
                    # Y軸がheading_vec, Z軸がup_vec, X軸がleft_vecとなるような回転行列を構築
                    rot_matrix = Matrix((left_vec, heading_vec, up_vec)).transposed() # 列ベクトルとして格納
                    leaf_obj_instance.rotation_mode = 'QUATERNION'
                    leaf_obj_instance.rotation_quaternion = rot_matrix.to_quaternion()
                    leaf_obj_instance.scale = (props.leaf_scale, props.leaf_scale, props.leaf_scale)
                else:
                    # 単純な平面の葉をbmeshで作成し、後で結合
                    leaf_bm = bmesh.new()
                    # 例: 4頂点の平面 (四角形)
                    v1 = leaf_bm.verts.new((-0.5 * props.leaf_scale, 0, 0))
                    v2 = leaf_bm.verts.new(( 0.5 * props.leaf_scale, 0, 0))
                    v3 = leaf_bm.verts.new(( 0.5 * props.leaf_scale, 1.0 * props.leaf_scale, 0)) # Y方向に伸びる葉
                    v4 = leaf_bm.verts.new((-0.5 * props.leaf_scale, 1.0 * props.leaf_scale, 0))
                    leaf_bm.faces.new((v1, v2, v3, v4))
                    
                    # このleaf_bmを現在のタートルの位置・向きに変換して、メインのbmにマージするか、
                    # 別オブジェクトとして作成する。ここではメインbmにマージする仮定は複雑なので、
                    # 別途、葉のオブジェクトを作成して配置する方がシンプル。上記leaf_objectの例を参照。
                    # もし1つのメッシュに含めたいなら、leaf_bmの頂点を変換してメインのbmに追加する。
                    
                    # 簡易的にメインのbmに葉のジオメトリを追加 (向きと位置を考慮)
                    # 回転と平行移動のための行列
                    transform_matrix = Matrix.Translation(position) @ Matrix((left_vec, heading_vec, up_vec)).transposed().to_4x4()

                    temp_leaf_verts = []
                    for v_idx in leaf_bm.verts:
                        v_world = transform_matrix @ v_idx.co
                        temp_leaf_verts.append(bm.verts.new(v_world))
                    
                    if len(temp_leaf_verts) == 4: # 4角形なら面を張る
                        try:
                            bm.faces.new(temp_leaf_verts)
                        except ValueError: # 頂点が縮退しているなど
                            pass
                    leaf_bm.free()


        # メインのメッシュを作成
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
    bl_category = 'Plant Gen' # サイドバーのタブ名

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Vogel's Model Section
        box_vogel = layout.box()
        box_vogel.label(text="Vogel Phyllotaxis", icon='OUTLINER_OB_POINTCLOUD')
        v_props = scene.vogel_props
        box_vogel.prop(v_props, "num_points")
        box_vogel.prop(v_props, "scaling_factor_c")

        # カスタムオブジェクトを使用するか、ICO球/頂点か
        box_vogel.prop(v_props, "use_custom_instance_object")

        if v_props.use_custom_instance_object:
            box_vogel.prop(v_props, "instance_object")
            box_vogel.prop(v_props, "instance_scale")
            box_vogel.prop(v_props, "align_to_normal")
        else:
            box_vogel.prop(v_props, "use_icospheres") # カスタムオブジェクトを使わない場合のみICO球か頂点かを選択
            if v_props.use_icospheres: # ICO球を使う場合のみポイントサイズ
                box_vogel.prop(v_props, "point_size")

        box_vogel.prop(v_props, "z_offset")
        box_vogel.prop(v_props, "z_factor_curvature")
        box_vogel.operator(VOGEL_OT_Generate.bl_idname, text="Generate Vogel Pattern")
 
        # L-System Section
        box_lsystem = layout.box()
        box_lsystem.label(text="L-System Plant", icon='MOD_TREE') #適切なアイコンに変更
        l_props = scene.lsystem_props
        box_lsystem.prop(l_props, "axiom")
        box_lsystem.prop(l_props, "rules_input")
        box_lsystem.prop(l_props, "iterations")
        box_lsystem.prop(l_props, "angle")
        box_lsystem.prop(l_props, "length")
        box_lsystem.prop(l_props, "initial_direction")
        
        row = box_lsystem.row()
        row.prop(l_props, "add_leaves")
        if l_props.add_leaves: # 葉を追加する場合のみ表示
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
    # プロパティグループをシーンに追加
    bpy.types.Scene.vogel_props = bpy.props.PointerProperty(type=VogelProperties)
    bpy.types.Scene.lsystem_props = bpy.props.PointerProperty(type=LSystemProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.vogel_props
    del bpy.types.Scene.lsystem_props

if __name__ == "__main__":
    # Blender内でテスト実行する場合（通常はBlenderがアドオンとして読み込む）
    # register()
    pass