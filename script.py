import bpy
import bmesh
import math
from types import SimpleNamespace

def doric_column_cfg(overrides = None) -> SimpleNamespace:
    
    base = {
        "scale": 0.955,
        
        # segments
        "vertical_seg": 1500,
        "radial_seg": 500,
        
        # horizontal
        "neck": 0.85,
        "echinus_top_ratio": 1.3,
        "abacus_overhang": 1.04,
        
        # vertical
        "total_height": 11,
        "capital_height": 1,
        "capital_distribution": (1, 1, 1),
        "annuli_range": 0.2,

        # fluting
        "flutes": 20,
        "flute_depth": 0.04,

        # entasis
        "entasis_amplitude": 0.035,
        "entasis_peak": 0.35,
        
        # annuli
        "annuli": 3,
        
        # abacus
        "chamfer": 0.02
    }
    
    if overrides:
        base.update(overrides)
    
    return SimpleNamespace(**base)

def merge_bmesh(bm, bm_add) -> bpy.types.Mesh:
    
    bm_add.verts.ensure_lookup_table()
    bm_add.faces.ensure_lookup_table()
    
    verts_map = {}
    for v in bm_add.verts:
        nv = bm.verts.new(v.co)
        verts_map[v] = nv
    
    for f in bm_add.faces:
        bm.faces.new([verts_map[v] for v in f.verts])
    
    bm_add.free()

def create_doric_mesh(cfg) -> bpy.types.Mesh:
    
    mesh = bpy.data.meshes.new("DoricColumnMesh")
    bm = bmesh.new()

    verts = [[None for _ in range(cfg.radial_seg)] for _ in range(cfg.vertical_seg + 1)]
    
    necking_height, echinus_height, abacus_height = (cfg.capital_height * x / sum(cfg.capital_distribution) for x in cfg.capital_distribution)
    echinus_radius = cfg.echinus_top_ratio * cfg.neck
    abacus_half = echinus_radius * cfg.abacus_overhang
    chamfer_len = cfg.chamfer * abacus_half
    
    neck_z = cfg.total_height - cfg.capital_height
    annuli_min = neck_z + (1 - cfg.annuli_range) * necking_height
    abacus_min = cfg.total_height - abacus_height
    
    def get_radius(z):
        if z <= neck_z:
            height_ratio = z / neck_z
            r = 1 - (1 - cfg.neck) * height_ratio
            # Entasis makes the column bulge in the middle
            if height_ratio <= cfg.entasis_peak:
                r *= 1 + cfg.entasis_amplitude * math.sin(0.5 * math.pi * height_ratio / cfg.entasis_peak)
            else:
                r *= 1 + cfg.entasis_amplitude * math.sin(0.5 * math.pi * (1 - height_ratio) / (1 - cfg.entasis_peak))
        else:
            # Sigmoid curve: from neck to echinus (abacus excluded)
            def sigmoid(x):
                return 1 / (1 + math.exp(-2 * x))
            def normalized_sigmoid(x):
                return (sigmoid(3 * x - 2) - sigmoid(-2)) / (sigmoid(1) - sigmoid(-2))
            height_ratio = (z - neck_z) / (necking_height + echinus_height)
            r = cfg.neck + (echinus_radius - cfg.neck) * normalized_sigmoid(height_ratio)
        return r
    
    def carve_flutes(z, r, theta):
        k = 0
        if z <= neck_z:
            k = 1
        elif z <= annuli_min:
            k = math.cos((z - neck_z) / (annuli_min - neck_z) * math.pi / 2) ** 2
        r *= 1 - k * cfg.flute_depth * math.fabs(math.sin(theta / 2 * cfg.flutes))
        return r
    
    def carve_annulus(z, c, r, dep):
        def normalized_cos(x):
            return math.cos(math.pi * x) / 2 + 0.5
        eps = 1e-3 * cfg.total_height
        if c - eps <= z <= c + eps:
            r -= dep * r * normalized_cos((z - c) / eps)
        return r
    
    for i in range(cfg.vertical_seg + 1):
        
        height_ratio = i / cfg.vertical_seg
        z = (cfg.total_height - abacus_height) * height_ratio
        
        r = get_radius(z)
        for j in range(cfg.annuli + 1):
            center = annuli_min + cfg.annuli_range * necking_height / cfg.annuli * j
            annulus_depth = 8e-3
            if j == 0:
                annulus_depth = 15e-3
            r = carve_annulus(z, center, r, annulus_depth)
        
        for j in range(cfg.radial_seg):
            theta = 2 * math.pi / cfg.radial_seg * j
            fluted_r = carve_flutes(z, r, theta)
            x = fluted_r * math.cos(theta)
            y = fluted_r * math.sin(theta)
            try:
                verts[i][j] = bm.verts.new((x * cfg.scale, y * cfg.scale, z * cfg.scale))
            except ValueError:
                pass

    for i in range(cfg.vertical_seg):
        for j in range(cfg.radial_seg):
            v1 = verts[i][j]
            v2 = verts[i][(j + 1) % cfg.radial_seg]
            v3 = verts[i + 1][(j + 1) % cfg.radial_seg]
            v4 = verts[i + 1][j]
            bm.faces.new((v1, v2, v3, v4))
    
    bm_abacus = bmesh.new()
    
    abacus_verts = []
    sgn = [-1, 1]
    cham = [1, 0, 0, 1]
    z_pos = [abacus_min, abacus_min + chamfer_len, cfg.total_height - chamfer_len, cfg.total_height]
    for ix in sgn:
        for iy in sgn:
            for k in range(4):
                x = ix * cfg.scale * (abacus_half - cham[k] * chamfer_len)
                y = iy * cfg.scale * (abacus_half - cham[k] * chamfer_len)
                z = z_pos[k] * cfg.scale
                abacus_verts.append(bm_abacus.verts.new((x, y, z)))
    
    abacus_faces = [(0, 4, 12, 8), (3, 7, 15, 11)]
    for i in range(3):
        abacus_faces.append((0 + i, 4 + i, 5 + i, 1 + i))
        abacus_faces.append((4 + i, 12 + i, 13 + i, 5 + i))
        abacus_faces.append((12 + i, 8 + i, 9 + i, 13 + i))
        abacus_faces.append((8 + i, 0 + i, 1 + i, 9 + i))
        
    for face in abacus_faces:
        bm_abacus.faces.new([abacus_verts[i] for i in face])
    
    merge_bmesh(bm, bm_abacus)
    
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.to_mesh(mesh)
    bm.free()
    
    for poly in mesh.polygons:
        if mesh.vertices[poly.vertices[0]].co.z < abacus_min * cfg.scale:
            poly.use_smooth = True
        else:
            poly.use_smooth = False
    
    return mesh

def create_doric_object(cfg, mesh = None, pos = (0, 0, 0)) -> bpy.types.Object:
    if mesh == None:
        mesh = create_doric_mesh(cfg)
    obj = bpy.data.objects.new("DoricColumn", mesh)
    obj.location = pos
    bpy.context.collection.objects.link(obj)
    return obj

if __name__ == "__main__":
    cfg = doric_column_cfg()
    create_doric_object(cfg)