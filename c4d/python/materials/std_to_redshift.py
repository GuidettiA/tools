"""
std_to_redshift.py — Convertit les matériaux à nodes Standard (import glTF/FBX/USD)
et les matériaux classiques en RS Standard Material (Redshift nodes).

- Agit sur les matériaux sélectionnés dans le Material Manager, ou sur tous si aucun n'est sélectionné.
- Couleur de base, métal, rugosité, normal map, émission, opacité (valeurs ou textures).
- Réassigne les tags de texture vers les nouveaux matériaux.
- Les originaux sont gardés et renommés avec SUFFIX_OLD (ou supprimés si DELETE_ORIGINALS).
- Passe le moteur de rendu sur Redshift (SET_RENDERER).
- Tout est annulable en un Ctrl+Z. Le rapport est affiché dans la console et copié dans le presse-papier.
"""
import os
import c4d
import maxon

SUFFIX_OLD = "_STD"
DELETE_ORIGINALS = False
SET_RENDERER = True

STD_SPACE = "net.maxon.nodespace.standard"
RS_SPACE = "com.redshift3d.redshift4c4d.class.nodespace"
RS_ENGINE = 1036219

P = "com.redshift3d.redshift4c4d.nodes.core."
RS_MAT = P + "standardmaterial"
RS_TEX = P + "texturesampler"
RS_SPLIT = P + "rscolorsplitter"
RS_BUMP = P + "bumpmap"

report = []


def log(msg):
    report.append(msg)


# ---------------------------------------------------------------- lecture (Standard)

def asset_id(node):
    try:
        v = node.GetValue("net.maxon.node.attribute.assetid")
    except Exception:
        return ""
    try:
        s = str(v[0])
    except Exception:
        s = str(v)
    s = s.strip()
    if s.startswith("("):
        s = s.strip("()").split(",")[0].strip()
    return s


def pval(port):
    if port is None:
        return None
    for fn in ("GetPortValue", "GetDefaultValue"):
        try:
            v = getattr(port, fn)()
            if v is not None:
                return v
        except Exception:
            pass
    return None


def kids(port):
    try:
        r = port.GetChildren()
        return list(r) if r else []
    except Exception:
        res = []
        port.GetChildren(lambda c: res.append(c) or True)
        return res


def inp(node, name):
    try:
        p = node.GetInputs().FindChild(name)
        return p if p and p.IsValid() else None
    except Exception:
        return None


def source(port):
    """(node source, id du port source) ou (None, None)."""
    if port is None:
        return None, None
    try:
        conns = port.GetConnections(maxon.PORT_DIR.INPUT)
    except Exception:
        return None, None
    for c in conns or []:
        src = c[0]
        return src.GetAncestor(maxon.NODE_KIND.NODE), str(src.GetId())
    return None, None


def resolve(port, depth=0):
    """Renvoie ('val', valeur) ou ('tex', url, canal|None)."""
    if port is None or depth > 12:
        return ("val", None)
    node, out_id = source(port)
    if node is None:
        return ("val", pval(port))
    a = asset_id(node)
    if a.endswith("generator.image"):
        return ("tex", pval(inp(node, "url")), None)
    if a.endswith("conversion.splitcolorcomponents"):
        r = resolve(inp(node, "color"), depth + 1)
        if r[0] == "tex":
            ch = out_id if out_id in ("r", "g", "b", "a") else None
            return ("tex", r[1], ch)
        return r
    if a == "net.maxon.node.type":
        return resolve(inp(node, "in"), depth + 1)
    if a.endswith("effect.blend"):
        return resolve(inp(node, "foreground"), depth + 1)
    # node inconnu : on garde la valeur locale du port
    log("   ! node non géré (%s), valeur par défaut gardée" % a)
    return ("val", pval(port))


def read_standard(graph):
    info = {"base": None, "metal": None, "rough": None, "normal": None,
            "emission": None, "alpha": None}
    nodes = []
    graph.GetRoot().GetInnerNodes(maxon.NODE_KIND.NODE, False, lambda n: nodes.append(n) or True)
    mnode = next((n for n in nodes if asset_id(n) == "net.maxon.render.node.material"), None)
    if mnode is None:
        raise RuntimeError("pas de node Material dans le graphe Standard")

    layers_port = inp(mnode, "bsdflayers")
    diffuse = metal = spec = None
    metal_strength = None
    for layer in kids(layers_port) if layers_port else []:
        bsdf = strength = None
        for c in kids(layer):
            cid = str(c.GetId())
            if cid.endswith("bsdflayer"):
                bsdf = source(c)[0]
            elif cid.endswith("strength"):
                strength = c
        if bsdf is None:
            continue
        btype = str(pval(inp(bsdf, "bsdftype")) or "")
        ftype = str(pval(inp(bsdf, "fresneltype")) or "")
        if "orennay" in btype or "lambert" in btype or ftype == "none":
            diffuse = diffuse or bsdf
        elif ftype == "conductor":
            metal, metal_strength = bsdf, strength
        else:
            sv = resolve(strength)
            if spec is None and not (sv[0] == "val" and sv[1] is not None and float(sv[1]) == 0.0):
                spec = bsdf

    if diffuse is not None:
        info["base"] = resolve(inp(diffuse, "color"))
    if metal_strength is not None:
        info["metal"] = resolve(metal_strength)
    rsrc = metal or spec
    if rsrc is not None:
        info["rough"] = resolve(inp(rsrc, "roughness"))
        if info["base"] is None:
            info["base"] = resolve(inp(rsrc, "color"))

    # normal : premier input connecté du node normal
    nnode = source(inp(mnode, "normal"))[0]
    if nnode is not None:
        for c in kids(nnode.GetInputs()):
            if source(c)[0] is not None:
                r = resolve(c)
                if r[0] == "tex":
                    info["normal"] = r
                break

    info["emission"] = resolve(inp(mnode, "emission"))
    info["alpha"] = resolve(inp(mnode, "alpha"))
    return info


# ---------------------------------------------------------------- lecture (classique)

def read_classic(mat):
    info = {"base": None, "metal": None, "rough": None, "normal": None,
            "emission": None, "alpha": None}

    def shader_tex(sh):
        if sh and sh.CheckType(c4d.Xbitmap):
            return ("tex", sh[c4d.BITMAPSHADER_FILENAME], None)
        return None

    try:
        info["base"] = shader_tex(mat[c4d.MATERIAL_COLOR_SHADER]) or ("val", mat[c4d.MATERIAL_COLOR_COLOR])
    except Exception:
        pass
    try:
        if mat[c4d.MATERIAL_USE_NORMAL]:
            info["normal"] = shader_tex(mat[c4d.MATERIAL_NORMAL_SHADER])
    except Exception:
        pass
    try:
        if mat[c4d.MATERIAL_USE_LUMINANCE]:
            info["emission"] = shader_tex(mat[c4d.MATERIAL_LUMINANCE_SHADER]) or ("val", mat[c4d.MATERIAL_LUMINANCE_COLOR])
    except Exception:
        pass
    return info


# ---------------------------------------------------------------- écriture (Redshift)

def setv(port, v):
    for fn in ("SetPortValue", "SetDefaultValue"):
        try:
            getattr(port, fn)(v)
            return True
        except Exception:
            pass
    return False


def as_color(v):
    try:
        return maxon.Color(float(v.r), float(v.g), float(v.b))
    except Exception:
        pass
    try:
        return maxon.Color(float(v.x), float(v.y), float(v.z))
    except Exception:
        f = float(v)
        return maxon.Color(f, f, f)


def as_float(v):
    try:
        return float(v)
    except Exception:
        try:
            return float(v.r)
        except Exception:
            return None


def is_black(c):
    return c is None or (c.r + c.g + c.b) < 1e-6


def abs_path(url, doc):
    s = str(url) if url is not None else ""
    if not s:
        return s
    for pre in ("relative:///", "file:///", "file://"):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    if os.path.isabs(s) and os.path.exists(s):
        return s
    base = doc.GetDocumentPath() or ""
    for cand in (os.path.join(base, s), os.path.join(base, "tex", s), os.path.join(base, "textures", s)):
        if os.path.exists(cand):
            return cand
    log("   ! texture introuvable sur disque : %s (chemin laissé tel quel)" % s)
    return s


def rs_texture(graph, path, raw):
    t = graph.AddChild(maxon.Id(), maxon.Id(RS_TEX))
    tex0 = t.GetInputs().FindChild(RS_TEX + ".tex0")
    pp = tex0.FindChild("path")
    if not setv(pp, maxon.Url(path)):
        setv(pp, path)
    if raw:
        cs = tex0.FindChild("colorspace")
        if cs and cs.IsValid():
            setv(cs, "RS_INPUT_COLORSPACE_RAW")
    return t


def rs_out(graph, tex_node, channel):
    """Port de sortie couleur ou canal (via Color Splitter)."""
    out = tex_node.GetOutputs().FindChild(RS_TEX + ".outcolor")
    if channel in (None, "rgb"):
        return out
    sp = graph.AddChild(maxon.Id(), maxon.Id(RS_SPLIT))
    out.Connect(sp.GetInputs().FindChild(RS_SPLIT + ".input"))
    return sp.GetOutputs().FindChild(RS_SPLIT + ".out" + channel)


def build_rs(doc, name, info):
    mat = c4d.BaseMaterial(c4d.Mmaterial)
    mat.SetName(name)
    nm = mat.GetNodeMaterialReference()
    graph = nm.CreateDefaultGraph(maxon.Id(RS_SPACE))
    nodes = []
    graph.GetRoot().GetInnerNodes(maxon.NODE_KIND.NODE, False, lambda n: nodes.append(n) or True)
    sm = next((n for n in nodes if asset_id(n) == RS_MAT), None)
    if sm is None:
        raise RuntimeError("graphe Redshift par défaut sans RS Standard Material")

    def port(pid):
        return sm.GetInputs().FindChild(RS_MAT + "." + pid)

    texcache = {}

    def tex(url, raw):
        key = (str(url), raw)
        if key not in texcache:
            texcache[key] = rs_texture(graph, abs_path(url, doc), raw)
        return texcache[key]

    done = []
    with graph.BeginTransaction() as tr:
        b = info.get("base")
        if b and b[0] == "tex":
            rs_out(graph, tex(b[1], False), b[2]).Connect(port("base_color"))
            done.append("base=tex")
        elif b and b[1] is not None:
            setv(port("base_color"), as_color(b[1]))
            done.append("base=couleur")

        m = info.get("metal")
        if m and m[0] == "tex":
            rs_out(graph, tex(m[1], True), m[2] or "b").Connect(port("metalness"))
            done.append("metal=tex")
        elif m and as_float(m[1]) is not None:
            setv(port("metalness"), as_float(m[1]))
            done.append("metal=%.3f" % as_float(m[1]))

        r = info.get("rough")
        if r and r[0] == "tex":
            rs_out(graph, tex(r[1], True), r[2] or "g").Connect(port("refl_roughness"))
            done.append("rough=tex")
        elif r and as_float(r[1]) is not None:
            setv(port("refl_roughness"), as_float(r[1]))
            done.append("rough=%.3f" % as_float(r[1]))

        n = info.get("normal")
        if n and n[0] == "tex":
            bump = graph.AddChild(maxon.Id(), maxon.Id(RS_BUMP))
            setv(bump.GetInputs().FindChild(RS_BUMP + ".inputtype"), maxon.Int32(1))
            tex(n[1], True).GetOutputs().FindChild(RS_TEX + ".outcolor").Connect(
                bump.GetInputs().FindChild(RS_BUMP + ".input"))
            bump.GetOutputs().FindChild(RS_BUMP + ".out").Connect(port("bump_input"))
            done.append("normal=tex")

        e = info.get("emission")
        if e and e[0] == "tex":
            rs_out(graph, tex(e[1], False), e[2]).Connect(port("emission_color"))
            setv(port("emission_weight"), 1.0)
            done.append("emission=tex")
        elif e and e[1] is not None and not is_black(as_color(e[1])):
            setv(port("emission_color"), as_color(e[1]))
            setv(port("emission_weight"), 1.0)
            done.append("emission=couleur")

        a = info.get("alpha")
        if a and a[0] == "tex":
            rs_out(graph, tex(a[1], True), a[2] or "a").Connect(port("opacity_color"))
            done.append("alpha=tex")
        elif a and as_float(a[1]) is not None and as_float(a[1]) < 0.999:
            f = as_float(a[1])
            setv(port("opacity_color"), maxon.Color(f, f, f))
            done.append("alpha=%.3f" % f)

        tr.Commit()
    return mat, done


# ---------------------------------------------------------------- scène

def walk(obj):
    while obj:
        yield obj
        for o in walk(obj.GetDown()):
            yield o
        obj = obj.GetNext()


def ensure_redshift(doc):
    rd = doc.GetActiveRenderData()
    if rd[c4d.RDATA_RENDERENGINE] == RS_ENGINE:
        return
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, rd)
    vp = rd.GetFirstVideoPost()
    has = False
    while vp:
        if vp.CheckType(RS_ENGINE):
            has = True
        vp = vp.GetNext()
    if not has:
        rd.InsertVideoPost(c4d.documents.BaseVideoPost(RS_ENGINE))
    rd[c4d.RDATA_RENDERENGINE] = RS_ENGINE
    log("Moteur de rendu passé sur Redshift.")


def main():
    doc = c4d.documents.GetActiveDocument()
    mats = [m for m in doc.GetMaterials() if m.GetBit(c4d.BIT_ACTIVE)] or doc.GetMaterials()
    tags = [t for o in walk(doc.GetFirstObject()) for t in o.GetTags() if t.CheckType(c4d.Ttexture)]

    doc.StartUndo()
    try:
        if SET_RENDERER:
            ensure_redshift(doc)
        n_ok = 0
        for old in mats:
            name = old.GetName()
            nm = old.GetNodeMaterialReference()
            try:
                if name.endswith(SUFFIX_OLD):
                    continue  # original déjà converti lors d'un passage précédent
                if nm and nm.HasSpace(maxon.Id(RS_SPACE)) and not nm.HasSpace(maxon.Id(STD_SPACE)):
                    log("%s : déjà Redshift, ignoré" % name)
                    continue
                if nm and nm.HasSpace(maxon.Id(STD_SPACE)):
                    info = read_standard(nm.GetGraph(maxon.Id(STD_SPACE)))
                    kind = "nodes Standard"
                elif old.CheckType(c4d.Mmaterial) and not (nm and nm.IsNodeBased()):
                    info = read_classic(old)
                    kind = "classique"
                else:
                    log("%s : type non géré, ignoré" % name)
                    continue

                new, done = build_rs(doc, name, info)
                if not DELETE_ORIGINALS:
                    # renommer l'original AVANT d'insérer, sinon C4D suffixe le nouveau en ".1"
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, old)
                    old.SetName(name + SUFFIX_OLD)
                doc.InsertMaterial(new, old)
                doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, new)
                new.SetName(name)

                n_tags = 0
                for t in tags:
                    if t[c4d.TEXTURETAG_MATERIAL] == old:
                        doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, t)
                        t[c4d.TEXTURETAG_MATERIAL] = new
                        n_tags += 1

                if DELETE_ORIGINALS:
                    doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, old)
                    old.Remove()
                else:
                    old.DelBit(c4d.BIT_ACTIVE)

                log("%s (%s) -> RS : %s | %d tag(s)" % (name, kind, ", ".join(done) or "rien lu", n_tags))
                n_ok += 1
            except Exception as ex:
                import traceback
                log("%s : ERREUR %s\n%s" % (name, ex, traceback.format_exc()))
        log("Terminé : %d matériau(x) converti(s)." % n_ok)
    finally:
        doc.EndUndo()
        c4d.EventAdd()

    txt = "\n".join(report)
    print(txt)
    c4d.CopyStringToClipboard(txt)


if __name__ == "__main__":
    main()
