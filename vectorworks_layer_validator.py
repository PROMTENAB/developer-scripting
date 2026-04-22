# -*- coding: utf-8 -*-
"""
Vectorworks 2026 - Regelverktyg (kompatibel, verifierad flytt + robust lager-val)
===============================================================================

Flöde:
1) Scriptet analyserar markerade objekt (fallback: aktivt lager)
2) Visar antal fel + grupper
3) I dialogen väljer du rader och åtgärd
4) Åtgärden sparas
5) När du trycker "Stäng" körs åtgärden

Not:
- EndLayoutDialog används INTE (saknas i din VW-version)
- Flytt använder designlager-handle (FLayer/NextLayer)
- Flytt verifieras efter försök
- Dropdown är ersatt med robust lagerlista + lagernummer-fält
"""

import vs

# =========================================================
# STATUS
# =========================================================
STATUS_OK = "OK"
STATUS_FEL_LAGER = "FEL_LAGER"
STATUS_INGEN_REGEL = "INGEN_REGEL"

# =========================================================
# REGLER
# =========================================================
RULES = [
    {"priority": 20, "type": "prefix", "match": "1.L-Byggnad",               "layer": "Mark"},
    {"priority": 20, "type": "prefix", "match": "1.L-Gränser",               "layer": "3.GRÄNSER"},
    {"priority": 20, "type": "prefix", "match": "1.L-Höjd",                  "layer": "Höjder -visuell"},
    {"priority": 20, "type": "prefix", "match": "1.L-Inhägnad",              "layer": "Mark"},
    {"priority": 10, "type": "prefix", "match": "1.L-Markhöjd",              "layer": "Höjder -visuell"},
    {"priority": 20, "type": "prefix", "match": "1.L-Mark",                  "layer": "Mark"},
    {"priority": 20, "type": "prefix", "match": "1.L-Sektion",               "layer": "Sektioner"},
    {"priority": 20, "type": "prefix", "match": "1.L-Utrustning",            "layer": "Utrustning"},
    {"priority": 20, "type": "prefix", "match": "1.L-Vegetationsyta",        "layer": "Plantering"},
    {"priority": 20, "type": "prefix", "match": "1.L-Växter",                "layer": "Plantering"},
    {"priority": 20, "type": "prefix", "match": "1.L-Växter-Träd-Nytt",      "layer": "Träd"},
    {"priority": 20, "type": "prefix", "match": "1.Modellinfo",              "layer": "7.MODELLSTÄMPEL"},
    {"priority": 20, "type": "prefix", "match": "1.Text-Littrering-Mark",    "layer": "Mark"},
    {"priority": 20, "type": "prefix", "match": "1.Text-Littrering-Plan",    "layer": "Plantering"},
    {"priority": 20, "type": "prefix", "match": "1.Text-Littrering-Utr",     "layer": "Utrustning"},
    {"priority": 20, "type": "prefix", "match": "1.Överby",                  "layer": "Överbyggnader"},
    {"priority": 20, "type": "prefix", "match": "1.Underlag",                "layer": "2.UNDERLAG"},
    {"priority": 10, "type": "prefix", "match": "1.Underlag-Inmätning",      "layer": "6.INMÄTNING"},
    {"priority": 10, "type": "prefix", "match": "1.Underlag-Grundkarta",     "layer": "4.GRUNDKARTA"},
    {"priority": 10, "type": "prefix", "match": "1.Underlag-Geoimage",       "layer": "5.GEOIMAGE + GIS"},
    {"priority": 20, "type": "prefix", "match": "1.Underlag-Bef.site",       "layer": "Model - befintlig (shuttle)"},
    {"priority": 20, "type": "prefix", "match": "Site-Gradelimit",           "layer": "Site model"},
    {"priority": 20, "type": "prefix", "match": "Site-MODELL",               "layer": "Site model"},
]

# =========================================================
# REGELMOTOR
# =========================================================
def _rule_matches(rule, class_name):
    rtype = rule.get("type")
    mv = rule.get("match", "")
    if rtype == "exact":
        return class_name == mv
    elif rtype == "prefix":
        return class_name.startswith(mv)
    elif rtype == "undantag":
        return class_name == mv
    return False


def _rule_sort_key(rule):
    type_order = {"exact": 0, "undantag": 1, "prefix": 2}
    return (
        int(rule.get("priority", 9999)),
        -len(rule.get("match", "")),
        type_order.get(rule.get("type"), 99),
    )


def match_rule(class_name):
    matches = [r for r in RULES if _rule_matches(r, class_name)]
    if not matches:
        return None
    matches.sort(key=_rule_sort_key)
    return matches[0]


def evaluate_class_layer(class_name, layer_name):
    rule = match_rule(class_name)
    if rule is None:
        return {"status": STATUS_INGEN_REGEL, "expected_layer": None, "matched_rule": None}

    expected = rule["layer"]
    rule_desc = "{}:{} (prio {})".format(rule["type"], rule["match"], rule["priority"])

    if layer_name == expected:
        return {"status": STATUS_OK, "expected_layer": expected, "matched_rule": rule_desc}
    return {"status": STATUS_FEL_LAGER, "expected_layer": expected, "matched_rule": rule_desc}


# =========================================================
# DATAINSAMLING / GRUPPERING
# =========================================================
def collect_objects(scope="selected"):
    handles = []

    def _cb(h):
        handles.append(h)

    if scope == "selected":
        vs.ForEachObject(_cb, "((SEL=TRUE))")
    elif scope == "active_layer":
        vs.ForEachObject(_cb, "((L=ActLayer))")
    else:
        raise ValueError("Ogiltigt scope: {} (selected/active_layer)".format(scope))

    return handles


def get_object_data(handle):
    class_name = vs.GetClass(handle) or ""
    layer_h = vs.GetLayer(handle)
    layer_name = vs.GetLName(layer_h) if layer_h else ""
    return {"handle": handle, "class_name": class_name, "layer_name": layer_name or ""}


def evaluate_object(handle):
    obj = get_object_data(handle)
    ev = evaluate_class_layer(obj["class_name"], obj["layer_name"])
    return {
        "handle": obj["handle"],
        "class_name": obj["class_name"],
        "layer_name": obj["layer_name"],
        "status": ev["status"],
        "expected_layer": ev["expected_layer"],
        "matched_rule": ev["matched_rule"],
    }


def group_results(results):
    groups = {}
    for r in results:
        if r["status"] not in (STATUS_FEL_LAGER, STATUS_INGEN_REGEL):
            continue

        class_name = r["class_name"]
        current_layer = r["layer_name"]
        suggested_layer = r["expected_layer"] if r["expected_layer"] else "None"
        key = (class_name, current_layer, suggested_layer, r["status"])

        if key not in groups:
            groups[key] = {
                "class_name": class_name,
                "current_layer": current_layer,
                "suggested_layer": suggested_layer,
                "status": r["status"],
                "count": 0,
                "handles": [],
            }

        groups[key]["count"] += 1
        groups[key]["handles"].append(r["handle"])

    return groups


def summarize(groups, total_checked):
    gl = list(groups.values())
    return {
        "total_checked": total_checked,
        "fel_lager_count": sum(g["count"] for g in gl if g["status"] == STATUS_FEL_LAGER),
        "ingen_regel_count": sum(g["count"] for g in gl if g["status"] == STATUS_INGEN_REGEL),
        "groups_sorted": sorted(gl, key=lambda g: (g["status"], g["class_name"], -g["count"])),
    }


def run_validation(scope="selected", fallback_to_active_layer=True):
    handles = collect_objects(scope=scope)
    used_scope = scope

    if scope == "selected" and not handles and fallback_to_active_layer:
        handles = collect_objects(scope="active_layer")
        used_scope = "active_layer"

    results = [evaluate_object(h) for h in handles]
    groups = group_results(results)
    summary = summarize(groups, len(results))

    return {
        "scope_used": used_scope,
        "results": results,
        "groups": groups,  # dict
        "summary": summary,
    }

# =========================================================
# UI STATE + ACTION
# =========================================================
FB_DID = 4000
FB_TEXT = 10
FB_ROWS = 11
FB_NEW_LAYER = 12
FB_LAYER_NUM = 13

FB_BTN_APPLY = 20
FB_BTN_ZOOM = 21
FB_BTN_SAMPLE = 22
FB_BTN_SELECT = 23
FB_BTN_MOVE = 24
FB_BTN_SHOW_LAYERS = 25
FB_BTN_PICK_LAYER = 26
FB_BTN_SHOW_GROUPS = 27
FB_BTN_PICK_MOVE_LAYERS = 28

SAMPLE_SIZE = 5

FB_STATE = {"groups": [], "did": None, "layer_names": [], "selected_move_layers": set()}
ACTION = {"name": None, "groups": [], "new_layer": None}


def _reset_action():
    ACTION["name"] = None
    ACTION["groups"] = []
    ACTION["new_layer"] = None


def _set_action_and_close(did, action_name, groups, new_layer=None):
    ACTION["name"] = action_name
    ACTION["groups"] = groups
    ACTION["new_layer"] = new_layer
    vs.AlrtDialog("Åtgärd sparad: {}.\nTryck 'Stäng' för att köra.".format(action_name))


# =========================================================
# UI HELPERS
# =========================================================
def _normalize_groups(groups):
    return list(groups.values()) if isinstance(groups, dict) else list(groups)


def _group_line(i, g):
    return "{:>2}. [{}] {} | {} -> {} | {} st".format(
        i + 1, g["status"], g["class_name"], g["current_layer"], g["suggested_layer"], g["count"]
    )


def _groups_as_lines(groups):
    return [_group_line(i, g) for i, g in enumerate(groups)]


def show_groups_dialog(groups, page_size=10):
    lines = _groups_as_lines(groups)
    if not lines:
        vs.AlrtDialog("Inga grupper att visa.")
        return

    total = len(lines)
    start = 0
    while start < total:
        end = min(start + page_size, total)
        msg = "Grupper {}-{} av {}:\n\n{}".format(start + 1, end, total, "\n".join(lines[start:end]))

        if end < total and hasattr(vs, "YNDialog"):
            if vs.YNDialog(msg + "\n\nVisa nästa sida?"):
                start = end
                continue
            break
        else:
            vs.AlrtDialog(msg)
            break


def _parse_rows(s, max_n):
    s = (s or "").strip()
    if not s:
        return []

    out = set()
    for part in s.split(","):
        p = part.strip()
        if not p:
            continue

        if "-" in p:
            a, b = p.split("-", 1)
            try:
                i, j = int(a), int(b)
            except Exception:
                continue
            if i > j:
                i, j = j, i
            for n in range(i, j + 1):
                if 1 <= n <= max_n:
                    out.add(n - 1)
        else:
            try:
                n = int(p)
            except Exception:
                continue
            if 1 <= n <= max_n:
                out.add(n - 1)

    return sorted(out)


def _collect_handles(groups):
    hs = []
    for g in groups:
        hs.extend(g.get("handles", []))
    return hs


def _bbox(handles):
    if not handles:
        return None
    first = True
    x1 = y1 = x2 = y2 = 0.0
    for h in handles:
        try:
            a, b, c, d = vs.GetBBox(h)
        except Exception:
            continue
        if first:
            x1, y1, x2, y2 = a, b, c, d
            first = False
        else:
            x1 = min(x1, a)
            y1 = min(y1, b)
            x2 = max(x2, c)
            y2 = max(y2, d)
    return None if first else (x1, y1, x2, y2)


def _zoom_bbox(b):
    if not b:
        return
    x1, y1, x2, y2 = b
    try:
        vs.ZoomRect(x1, y1, x2, y2)
        return
    except Exception:
        pass
    try:
        vs.SetZoomRect(x1, y1, x2, y2)
    except Exception:
        pass


# ---------- Lagerhantering ----------
def _find_layer_by_name(layer_name):
    h = vs.FLayer()
    while h:
        try:
            if vs.GetLName(h) == layer_name:
                return h
        except Exception:
            pass
        h = vs.NextLayer(h)
    return None


def _get_or_create_layer(layer_name):
    if not layer_name:
        return None

    h = _find_layer_by_name(layer_name)
    if h:
        return h

    try:
        vs.Layer(layer_name)  # försök skapa
    except Exception:
        pass

    return _find_layer_by_name(layer_name)


def _move_handles_to_layer(handles, layer_name):
    target_layer = _get_or_create_layer(layer_name)
    if not target_layer:
        return 0, len(handles)

    ok = 0
    fail = 0

    for h in handles:
        moved = False

        # A) SetParent
        try:
            vs.SetParent(h, target_layer)
            cur_h = vs.GetLayer(h)
            cur_name = vs.GetLName(cur_h) if cur_h else ""
            if cur_name == layer_name:
                moved = True
        except Exception:
            pass

        # B) SetLayer fallback
        if (not moved) and hasattr(vs, "SetLayer"):
            try:
                vs.SetLayer(h, target_layer)
                cur_h = vs.GetLayer(h)
                cur_name = vs.GetLName(cur_h) if cur_h else ""
                if cur_name == layer_name:
                    moved = True
            except Exception:
                pass

        if moved:
            ok += 1
        else:
            fail += 1

    try:
        vs.ReDrawAll()
    except Exception:
        pass

    return ok, fail


def _get_design_layer_names():
    names = []
    h = vs.FLayer()
    while h:
        try:
            names.append(vs.GetLName(h))
        except Exception:
            pass
        h = vs.NextLayer(h)
    return sorted(list(set(names)))


def _layer_lines(layer_names):
    return ["{:>3}. {}".format(i + 1, n) for i, n in enumerate(layer_names)]


def show_layers_dialog(layer_names, page_size=20):
    if not layer_names:
        vs.AlrtDialog("Inga lager hittades.")
        return

    lines = _layer_lines(layer_names)
    total = len(lines)
    start = 0

    while start < total:
        end = min(start + page_size, total)
        msg = "Lager {}-{} av {}:\n\n{}".format(start + 1, end, total, "\n".join(lines[start:end]))

        if end < total and hasattr(vs, "YNDialog"):
            if vs.YNDialog(msg + "\n\nVisa nästa sida?"):
                start = end
                continue
            break
        else:
            vs.AlrtDialog(msg)
            break


def _pick_layer_by_number(dialog):
    layer_names = FB_STATE.get("layer_names", [])
    raw = (vs.GetItemText(dialog, FB_LAYER_NUM) or "").strip()
    if not raw:
        vs.AlrtDialog("Ange lagernummer först (ex: 3).")
        return

    try:
        n = int(raw)
    except Exception:
        vs.AlrtDialog("Lagernummer måste vara ett heltal.")
        return

    if n < 1 or n > len(layer_names):
        vs.AlrtDialog("Lagernummer utanför intervall 1-{}.".format(len(layer_names)))
        return

    picked = layer_names[n - 1]
    vs.SetItemText(dialog, FB_NEW_LAYER, picked)
    vs.AlrtDialog("Valt lager: {}".format(picked))


def _rows_to_compact_text(idxs):
    if not idxs:
        return ""
    nums = sorted(set(i + 1 for i in idxs))
    ranges = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append("{}-{}".format(start, prev) if start != prev else str(start))
        start = prev = n
    ranges.append("{}-{}".format(start, prev) if start != prev else str(start))
    return ",".join(ranges)


def _unique_current_layers(groups):
    out = set()
    for g in groups:
        ln = (g.get("current_layer", "") or "").strip()
        if ln:
            out.add(ln)
    return sorted(list(out))


def _group_idxs_for_layers(groups, layer_names):
    allowed = set(layer_names)
    return [i for i, g in enumerate(groups) if g.get("current_layer", "") in allowed]


def _choose_move_layers_with_checkboxes(groups, preselected):
    all_layers = _unique_current_layers(groups)
    if not all_layers:
        vs.AlrtDialog("Inga lager hittades i grupperna.")
        return set(preselected)

    PAGE_SIZE = 12
    CHK_BASE = 200
    BTN_PREV = 300
    BTN_NEXT = 301
    BTN_ALL = 302
    BTN_NONE = 303
    TXT_INFO = 304

    state = {"page": 0, "sel": set(preselected), "did": None}
    pages = (len(all_layers) + PAGE_SIZE - 1) // PAGE_SIZE

    did = vs.CreateLayout("Välj lager att flytta (checkboxar)", False, "OK", "Avbryt")
    state["did"] = did
    vs.CreateStaticText(did, TXT_INFO, "", 60)
    for i in range(PAGE_SIZE):
        vs.CreateCheckBox(did, CHK_BASE + i, "")
    vs.CreatePushButton(did, BTN_PREV, "Föregående")
    vs.CreatePushButton(did, BTN_NEXT, "Nästa")
    vs.CreatePushButton(did, BTN_ALL, "Markera alla")
    vs.CreatePushButton(did, BTN_NONE, "Rensa alla")

    vs.SetFirstLayoutItem(did, TXT_INFO)
    for i in range(PAGE_SIZE):
        if i == 0:
            vs.SetBelowItem(did, TXT_INFO, CHK_BASE + i, 4, 0)
        else:
            vs.SetBelowItem(did, CHK_BASE + i - 1, CHK_BASE + i, 2, 0)
    vs.SetBelowItem(did, CHK_BASE + PAGE_SIZE - 1, BTN_PREV, 8, 0)
    vs.SetRightItem(did, BTN_PREV, BTN_NEXT, 8, 0)
    vs.SetRightItem(did, BTN_NEXT, BTN_ALL, 8, 0)
    vs.SetRightItem(did, BTN_ALL, BTN_NONE, 8, 0)

    def _page_slice():
        p = state["page"]
        a = p * PAGE_SIZE
        b = min(a + PAGE_SIZE, len(all_layers))
        return a, b

    def _save_page():
        a, b = _page_slice()
        for i in range(PAGE_SIZE):
            idx = a + i
            if idx >= b:
                continue
            name = all_layers[idx]
            checked = bool(vs.GetBooleanItem(did, CHK_BASE + i))
            if checked:
                state["sel"].add(name)
            else:
                state["sel"].discard(name)

    def _load_page():
        a, b = _page_slice()
        vs.SetItemText(did, TXT_INFO, "Lager {}-{} av {} (sida {}/{})".format(a + 1, b, len(all_layers), state["page"] + 1, pages))
        for i in range(PAGE_SIZE):
            idx = a + i
            cid = CHK_BASE + i
            if idx < b:
                nm = all_layers[idx]
                vs.SetItemText(did, cid, "{}. {}".format(idx + 1, nm))
                try:
                    vs.SetBooleanItem(did, cid, nm in state["sel"])
                except Exception:
                    pass
                try:
                    vs.EnableItem(did, cid, True)
                except Exception:
                    pass
            else:
                vs.SetItemText(did, cid, "")
                try:
                    vs.SetBooleanItem(did, cid, False)
                except Exception:
                    pass
                try:
                    vs.EnableItem(did, cid, False)
                except Exception:
                    pass

    _load_page()

    def _handler(item, data):
        if item == BTN_PREV:
            _save_page()
            if state["page"] > 0:
                state["page"] -= 1
            _load_page()
        elif item == BTN_NEXT:
            _save_page()
            if state["page"] < pages - 1:
                state["page"] += 1
            _load_page()
        elif item == BTN_ALL:
            state["sel"] = set(all_layers)
            _load_page()
        elif item == BTN_NONE:
            state["sel"] = set()
            _load_page()
        return item

    result = vs.RunLayoutDialog(did, _handler)
    _save_page()
    if result == 1:
        return set(state["sel"])
    return set(preselected)


# =========================================================
# Requested action functions
# =========================================================
def zoom_to_group(groups):
    hs = _collect_handles(groups)
    if not hs:
        vs.AlrtDialog("Välj rader först (ex: 1,3,5-7).")
        return
    _zoom_bbox(_bbox(hs))


def highlight_sample(groups):
    hs = _collect_handles(groups)
    if not hs:
        vs.AlrtDialog("Välj rader först.")
        return

    sample = hs[:SAMPLE_SIZE]
    try:
        vs.DSelectAll()
    except Exception:
        pass

    c = 0
    for h in sample:
        try:
            vs.SetSelect(h)
            c += 1
        except Exception:
            pass

    _zoom_bbox(_bbox(sample))
    vs.AlrtDialog("Exempel markerade: {} objekt.".format(c))


def select_all(groups):
    hs = _collect_handles(groups)
    if not hs:
        vs.AlrtDialog("Välj rader först.")
        return

    try:
        vs.DSelectAll()
    except Exception:
        pass

    c = 0
    for h in hs:
        try:
            vs.SetSelect(h)
            c += 1
        except Exception:
            pass

    _zoom_bbox(_bbox(hs))
    vs.AlrtDialog("Markerade: {} objekt.".format(c))


def confirm_move(groups):
    if not groups:
        vs.AlrtDialog("Välj rader först.")
        return False

    total = sum(len(g.get("handles", [])) for g in groups)
    g0 = groups[0]
    msg = "Flytta {} objekt från '{}' till '{}'{}?".format(
        total,
        g0.get("current_layer", ""),
        g0.get("suggested_layer", ""),
        " (flera grupper)" if len(groups) > 1 else ""
    )

    try:
        return bool(vs.YNDialog(msg))
    except Exception:
        vs.AlrtDialog(msg + "\n\n(YNDialog saknas)")
        return False


# =========================================================
# UI functions
# =========================================================
def build_dialog(groups):
    FB_STATE["groups"] = _normalize_groups(groups)
    FB_STATE["layer_names"] = _get_design_layer_names()

    did = vs.CreateLayout("Regelavvikelser - Grupper", False, "Stäng", "")
    FB_STATE["did"] = did

    vs.CreateStaticText(did, 100, "Grupper (klicka 'Visa grupper'):", 35)
    vs.CreateEditText(did, FB_TEXT, "", 100)

    vs.CreateStaticText(did, 101, "Välj rader (ex: 1,3,5-7):", 28)
    vs.CreateEditText(did, FB_ROWS, "", 28)

    vs.CreateStaticText(did, 102, "Nytt föreslaget lager:", 30)
    vs.CreateEditText(did, FB_NEW_LAYER, "", 30)

    vs.CreateStaticText(did, 103, "Lagernummer (från 'Visa lager'):", 30)
    vs.CreateEditText(did, FB_LAYER_NUM, "", 10)

    vs.CreatePushButton(did, FB_BTN_SHOW_LAYERS, "Visa lager")
    vs.CreatePushButton(did, FB_BTN_PICK_LAYER, "Välj lager")
    vs.CreatePushButton(did, FB_BTN_APPLY, "Sätt lager på valda")
    vs.CreatePushButton(did, FB_BTN_SHOW_GROUPS, "Visa grupper")
    vs.CreatePushButton(did, FB_BTN_PICK_MOVE_LAYERS, "Välj lager att flytta")
    vs.CreatePushButton(did, FB_BTN_ZOOM, "Zooma till")
    vs.CreatePushButton(did, FB_BTN_SAMPLE, "Visa exempel (5)")
    vs.CreatePushButton(did, FB_BTN_SELECT, "Markera alla")
    vs.CreatePushButton(did, FB_BTN_MOVE, "Flytta valda...")

    vs.SetFirstLayoutItem(did, 100)
    vs.SetBelowItem(did, 100, FB_TEXT, 4, 0)

    vs.SetBelowItem(did, FB_TEXT, 101, 8, 0)
    vs.SetRightItem(did, 101, FB_ROWS, 8, 0)

    vs.SetBelowItem(did, 101, 102, 8, 0)
    vs.SetRightItem(did, 102, FB_NEW_LAYER, 8, 0)

    vs.SetBelowItem(did, 102, 103, 6, 0)
    vs.SetRightItem(did, 103, FB_LAYER_NUM, 8, 0)
    vs.SetRightItem(did, FB_LAYER_NUM, FB_BTN_SHOW_LAYERS, 8, 0)
    vs.SetRightItem(did, FB_BTN_SHOW_LAYERS, FB_BTN_PICK_LAYER, 8, 0)
    vs.SetRightItem(did, FB_BTN_PICK_LAYER, FB_BTN_APPLY, 8, 0)

    vs.SetBelowItem(did, 103, FB_BTN_SHOW_GROUPS, 10, 0)
    vs.SetRightItem(did, FB_BTN_SHOW_GROUPS, FB_BTN_PICK_MOVE_LAYERS, 8, 0)
    vs.SetRightItem(did, FB_BTN_PICK_MOVE_LAYERS, FB_BTN_ZOOM, 8, 0)
    vs.SetRightItem(did, FB_BTN_ZOOM, FB_BTN_SAMPLE, 8, 0)
    vs.SetRightItem(did, FB_BTN_SAMPLE, FB_BTN_SELECT, 8, 0)
    vs.SetRightItem(did, FB_BTN_SELECT, FB_BTN_MOVE, 8, 0)

    populate_list(did, FB_STATE["groups"])
    return did


def populate_list(dialog, groups):
    txt = "Totalt grupper: {}. Klicka 'Visa grupper' för numrerad lista.".format(len(groups))
    vs.SetItemText(dialog, FB_TEXT, txt)


def get_selected_groups(dialog):
    idxs = _parse_rows(vs.GetItemText(dialog, FB_ROWS), len(FB_STATE["groups"]))
    return [FB_STATE["groups"][i] for i in idxs]


def _dialog_handler(item, data):
    did = FB_STATE["did"]

    if item == FB_BTN_SHOW_GROUPS:
        show_groups_dialog(FB_STATE["groups"], page_size=10)

    elif item == FB_BTN_SHOW_LAYERS:
        show_layers_dialog(FB_STATE.get("layer_names", []), page_size=20)

    elif item == FB_BTN_PICK_LAYER:
        _pick_layer_by_number(did)

    elif item == FB_BTN_PICK_MOVE_LAYERS:
        selected_layers = _choose_move_layers_with_checkboxes(FB_STATE["groups"], FB_STATE.get("selected_move_layers", set()))
        FB_STATE["selected_move_layers"] = set(selected_layers)
        idxs = _group_idxs_for_layers(FB_STATE["groups"], selected_layers)
        rows_txt = _rows_to_compact_text(idxs)
        vs.SetItemText(did, FB_ROWS, rows_txt)
        vs.AlrtDialog("Valda lager: {} st.\nMatchande grupper: {} st.".format(len(selected_layers), len(idxs)))

    elif item == FB_BTN_APPLY:
        selected = get_selected_groups(did)
        new_layer = (vs.GetItemText(did, FB_NEW_LAYER) or "").strip()

        if new_layer.upper() == "TRÄD":
            new_layer = "Träd"

        if not selected:
            vs.AlrtDialog("Välj rader först.")
        elif not new_layer:
            vs.AlrtDialog("Ange lager manuellt eller välj via lagernummer + 'Välj lager'.")
        else:
            _set_action_and_close(did, "apply_layer", selected, new_layer)

    elif item == FB_BTN_ZOOM:
        selected = get_selected_groups(did)
        if not selected:
            vs.AlrtDialog("Välj rader först.")
        else:
            _set_action_and_close(did, "zoom", selected)

    elif item == FB_BTN_SAMPLE:
        selected = get_selected_groups(did)
        if not selected:
            vs.AlrtDialog("Välj rader först.")
        else:
            _set_action_and_close(did, "sample", selected)

    elif item == FB_BTN_SELECT:
        selected = get_selected_groups(did)
        if not selected:
            vs.AlrtDialog("Välj rader först.")
        else:
            _set_action_and_close(did, "select_all", selected)

    elif item == FB_BTN_MOVE:
        selected = get_selected_groups(did)
        if not selected:
            vs.AlrtDialog("Välj rader först.")
        else:
            _set_action_and_close(did, "move", selected)

    return item


def run_ui(groups):
    did = build_dialog(groups)
    _reset_action()
    vs.RunLayoutDialog(did, _dialog_handler)


# =========================================================
# Execute action AFTER dialog closes
# =========================================================
def _execute_action():
    name = ACTION["name"]
    groups = ACTION["groups"]
    new_layer = ACTION["new_layer"]

    if not name or not groups:
        return

    if name == "zoom":
        zoom_to_group(groups)

    elif name == "sample":
        highlight_sample(groups)

    elif name == "select_all":
        select_all(groups)

    elif name == "apply_layer":
        for g in groups:
            g["suggested_layer"] = new_layer
        vs.AlrtDialog("Föreslaget lager uppdaterat för {} grupp(er).".format(len(groups)))

    elif name == "move":
        if not confirm_move(groups):
            return

        total = 0
        moved = 0
        failed = 0

        for g in groups:
            hs = g.get("handles", [])
            target = g.get("suggested_layer", "")
            total += len(hs)
            ok, fail = _move_handles_to_layer(hs, target)
            moved += ok
            failed += fail

        vs.AlrtDialog(
            "Flytt klar.\nTotalt: {}\nFlyttade: {}\nMisslyckade: {}".format(total, moved, failed)
        )


# =========================================================
# MAIN
# =========================================================
def main():
    try:
        report = run_validation(scope="selected", fallback_to_active_layer=True)
        s = report["summary"]

        vs.AlrtDialog(
            "Kontrollerade: {}\nFEL_LAGER: {}\nINGEN_REGEL: {}\nGrupper: {}".format(
                s["total_checked"], s["fel_lager_count"], s["ingen_regel_count"], len(report["groups"])
            )
        )

        run_ui(report["groups"])
        _execute_action()

    except Exception as e:
        vs.AlrtDialog("Fel i script:\n{}".format(e))


main()
