from PIL import Image, ImageGrab
import collections
from constants import *
from display_overlay import register_overlay_hot_keys, reset_feasible_recipes_and_update
from parse_screenshot import get_grid_coords, create_icons, get_grid_from_mask
import win32gui
import time
import keyboard
from create_grid_images import create_grid_descriptor, recipe_to_coords


def process_refs_values():
    refs_values = {}
    for ref_name in CONST_COMPONENTS | CONST_RECIPES | {"Empty":"whatevs"}:
        try:
            refs_values[ref_name] = Image.open(f"refs/ref{ref_name}.png").histogram()
        except FileNotFoundError:
                print("ERROR REFERENCE NOT FOUND", ref_name)
    return refs_values


def distance(a, b):
    res = 0
    assert len(a) == len(b)
    for i in range(len(a)):
        res += (a[i] - b[i]) ** 2

    return res

def run_query(query, refs_values):
    best_dist = float("inf")
    best_idx = -1
    for ref_name in CONST_COMPONENTS | CONST_RECIPES | {"Empty":"whatevs"}:
        if ref_name not in refs_values:
            # print(ref_name, "has no reference")
            continue
        dist = distance(query, refs_values[ref_name])
        if dist < best_dist:
            best_dist = dist
            best_idx = ref_name
            # print(f"Distance to ref {ref_name}: {dist}")


    # print(f"Final solution : {best_idx}")
    return best_idx

# the catalogue is a counter of what we have
def build_catalogue(refs_values):
    catalogue = {}
    debug_grid = [[],[],[],[],[],[],[],[]]
    for x in range(8):
        debug_line = []
        for y in range(8):
            test_id=str(x) + str(y)
            try:
                query = Image.open(f"arch_icons/{test_id}.png").histogram()
                # print(f"processing {test_id}")
                organ = run_query(query, refs_values)
                debug_line.append(organ)
                if organ != "Empty":
                    if organ in catalogue:
                        catalogue[organ] += [(x,y)]
                    else:
                        catalogue[organ] = [(x,y)]
            except FileNotFoundError:
                print("ERROR GRID ELEMENT NOT FOUND")
        for z in range(8):
            debug_grid[z].append(debug_line[z])

    return catalogue, debug_grid

def build_organ_specific_subtree(organ, catalogue, offset):
    organ_count = len(catalogue[organ]) if organ in catalogue else 0
    if organ in CONST_RECIPES:
        if organ in catalogue:
            badge = _TEMPLATE_HTML_SIMPLE_COUNT_SOME % organ_count
        else:
            badge = _TEMPLATE_HTML_SIMPLE_COUNT_NONE % organ_count

        if set(CONST_RECIPES[organ]).issubset(set(catalogue.keys())):
            display_organ = _TEMPLATE_HTML_CRAFTABLE % (badge, organ)
        else:
            display_organ = _TEMPLATE_HTML_NOT_CRAFTABLE % (badge, organ)
    else:
        if organ in catalogue:
            display_organ = _TEMPLATE_HTML_OWNED % (organ_count, organ)
        else:
            display_organ = _TEMPLATE_HTML_NOT_OWNED % (0, organ)
        return _TEMPLATE_HTML_TREE_NODE % (offset*"&nbsp;"*10, display_organ, "")
        
    subs = ""
    for sub_organ in CONST_RECIPES[organ]:
        subs += build_organ_specific_subtree(sub_organ, catalogue, offset+1)
    

    return _TEMPLATE_HTML_TREE_NODE % (offset*"&nbsp;"*10, display_organ, subs)

def build_goal_missing_organs(organ, catalogue):
    display = ""
    if organ in CONST_COMPONENTS:
        if organ not in catalogue:
            return _TEMPLATE_HTML_NOT_OWNED % (0, organ) +  "<br/>"
    
    if organ not in catalogue:
        for sub_organ in CONST_RECIPES[organ]:
            display += build_goal_missing_organs(sub_organ, catalogue)
    

    return display


def build_and_write_html_result(catalogue):
    # for name, recipe in CONST_RECIPES.items():
    #     if set(recipe).issubset(set(catalogue.keys())):
    #         print(name)

    droppable = ""
    for name in (CONST_COMPONENTS):
        if name in catalogue:
            droppable += _TEMPLATE_HTML_OWNED % (len(catalogue[name]), name)
        else:
            droppable += _TEMPLATE_HTML_NOT_OWNED % (0, name)


    crafted = ""
    for name in (CONST_RECIPES):
        if name in catalogue:
            crafted += _TEMPLATE_HTML_OWNED % (len(catalogue[name]), name)
        else:
            crafted += _TEMPLATE_HTML_NOT_OWNED % (0, name)

    inventory = _TEMPLATE_HTML_INVENTORY % (droppable, crafted)
    grid_id = 0
    recipesHTML = ""
    for crafted, recipe in CONST_RECIPES.items():
        compos = ""
        for name in recipe:
            if name in catalogue:
                compos += _TEMPLATE_HTML_OWNED % (len(catalogue[name]), name) + "<br/>"
            else:
                compos += _TEMPLATE_HTML_NOT_OWNED % (0, name) + "<br/>"

        products = ""
        for name, sub_recipe in CONST_RECIPES.items():
            if crafted in sub_recipe:
                name_count = len(catalogue[name]) if name in catalogue else 0
                products += _TEMPLATE_HTML_CUSTOM_COLOR % (CONST_TIER_COLORS[CONST_RECIPES_TIERS[name]],name_count, name) + "<br/>"

        line = ""
        crafted_count = len(catalogue[crafted]) if crafted in catalogue else 0
        if crafted in catalogue:
            line = _TEMPLATE_HTML_SIMPLE_COUNT_SOME % crafted_count + crafted
        else:
            line = _TEMPLATE_HTML_SIMPLE_COUNT_NONE % crafted_count + crafted
        if set(recipe).issubset(set(catalogue.keys())):
            create_grid_descriptor(recipe_to_coords(recipe, catalogue), grid_id)
            recipesHTML = _TEMPLATE_HTML_RECIPE_OK % (line, compos, products, grid_id) + recipesHTML
            grid_id += 1
        else:

            recipesHTML = recipesHTML + _TEMPLATE_HTML_RECIPE_KO % (line, compos, products)

    tree = ""
    for organ in CONST_BIG_TICKET_ORGANS:
        tree += build_organ_specific_subtree(organ, catalogue, 0)

    goals = ""
    for organ in CONST_GOALS_ORGANS:
        organ_count = len(catalogue[organ]) if organ in catalogue else 0
        if organ_count > 0:
            badge = _TEMPLATE_HTML_SIMPLE_COUNT_SOME % organ_count
        else:
            badge = _TEMPLATE_HTML_SIMPLE_COUNT_NONE % organ_count

        if set(CONST_RECIPES[organ]).issubset(set(catalogue.keys())):
            display_organ = _TEMPLATE_HTML_CRAFTABLE % (badge, organ)
        else:
            display_organ = _TEMPLATE_HTML_NOT_CRAFTABLE % (badge, organ)
        goals += _TEMPLATE_HTML_GOAL_BASE % (display_organ, build_goal_missing_organs(organ, catalogue))

    content = _TEMPLATE_HTML_PAGE % (goals, inventory, recipesHTML, tree)
    return content



def save_screenshot():
    toplist, winlist = [], []
    def enum_cb(hwnd, results):
        winlist.append((hwnd, win32gui.GetWindowText(hwnd)))
    win32gui.EnumWindows(enum_cb, toplist)

    poe = [(hwnd, title) for hwnd, title in winlist if 'exile' in title.lower()]
    # just grab the hwnd for first window matching firefox
    poe = poe[0]
    hwnd = poe[0]

    win32gui.SetForegroundWindow(hwnd)
    bbox = win32gui.GetWindowRect(hwnd)
    im = ImageGrab.grab(bbox)
    box = (100 , 300, 540, 770)
    crop = im.crop(box)
    crop.save("arch.png", "png")





def main():
    catalogue = {}

    register_overlay_hot_keys(
        "exile",
        lambda: catalogue,
        100, 300, 540, 770
    )
    def reset_overlay_recipe():
        reset_feasible_recipes_and_update(
            "exile",
            catalogue,
            100, 300, 540, 770
        )

    while True:
        # wait = 0
        save_screenshot()
        im = Image.open("arch.png")
        px=im.load()
        # cols, lines = get_grid_coords(im, px)
        cols, lines = get_grid_from_mask()
        create_icons(im, px, cols, lines)

        refs_values = process_refs_values()
        catalogue, debug_grid = build_catalogue(refs_values)
        content = build_and_write_html_result(catalogue)
        for line in debug_grid:
            print(line)
        with open("ArchnemCatalogue.html", 'w') as file:
            file.write(content)

        reset_overlay_recipe()
        keyboard.wait("F2")
        time.sleep(0.2)


if __name__ == "__main__":
    main()

        