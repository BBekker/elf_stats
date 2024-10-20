from squarify import normalize_sizes, squarify

from bokeh.plotting import figure, ColumnDataSource
from bokeh.transform import factor_cmap
from bokeh.layouts import layout
import parser

from bokeh.io import curdoc
from bokeh.models.widgets import FileInput, Slider
from pybase64 import b64decode
import io

square_size = {"x": 0, "y": 0, "dx": 1000, "dy": 800}
variables = []
treemap_data = []

datasource = ColumnDataSource({"x": [], "y": [], "dx": [], "dy": [], "name": []})

max_depth = 10


def generate_treemap_data():
    treemap_data.clear()
    variables.sort(key=lambda x: x.type.size)
    sizes = [x.type.size for x in variables]
    print(sizes, square_size)
    normalized_sizes = normalize_sizes(sizes, square_size['dx'], square_size['dy'])
    print(square_size)
    squares = squarify(normalized_sizes, **square_size)
    for node, square in zip(variables, squares):
        add_if_leaf(node, max_depth - 1, square, node.name)

    #transpose to column data
    column_data = {"x": [], "y": [], "dx": [], "dy": [], "name": []}
    column_data["x"] = [x["x"] for x in treemap_data]
    column_data["y"] = [x["y"] for x in treemap_data]
    column_data["dx"] = [x["dx"] for x in treemap_data]
    column_data["dy"] = [x["dy"] for x in treemap_data]
    column_data["name"] = [x["name"] for x in treemap_data]
    datasource.data = column_data




def add_if_leaf(node: parser.Variable, depth: int, input_square: dict[int, int, int, int], path_name: str):
    """
       if max depth is 0, or we are at a leaf node, add a square for this node.
       else, loop through children
       - calculate a square for each child and call function recursively
    """
    if depth == 0 or (not isinstance(node.type, parser.Struct) and not isinstance(node.type, parser.Array)) :
        treemap_data.append({"name": node.type.name+" "+path_name, **input_square})
    else:
        if isinstance(node.type, parser.Struct):
            children: list[parser.Variable] = node.type.members
            children.sort(key=lambda x: x.type.size)
            sizes = [x.type.size for x in children]
        elif isinstance(node.type, parser.Array):
            assert isinstance(node.type, parser.Array)
            children = [parser.Variable(tag="", die_offset=0, name=f"[{i}]", location=0, type=node.type.array_elements) for i in range(node.type.array_size)]
            sizes = [node.type.array_elements.size] * node.type.array_size
        else:
            assert False, "PANIC!"
        normalized_sizes = normalize_sizes(sizes, input_square['dx'], input_square['dy'])
        squares = squarify(normalized_sizes, **input_square)
        for node, square in zip(children, squares):
            add_if_leaf(node, depth - 1, square, path_name+"."+node.name)
    




def upload_elf(attr, old, new):
    print("fit data upload succeeded")

    decoded = b64decode(new)
    f = io.BytesIO(decoded)
    elffile = parser.ELFFile(f)

    dwarfinfo = elffile.get_dwarf_info()
    cus = dwarfinfo.iter_CUs()
    global variables
    for CU in cus:
        print(
                "  Found a compile unit at offset %s, length %s, name %s"
                % (CU.cu_offset, CU["unit_length"], CU.get_top_DIE().get_full_path())
            )
        sub_variables = parser.get_variables(CU)
        variables += sub_variables
    
    generate_treemap_data()

def update_depth(attr, old, new):
    print("depth updated")
    global max_depth
    max_depth = new
    generate_treemap_data()
    

file_input = FileInput(accept=".elf, .axf")
file_input.on_change('value', upload_elf)

depth_slider = Slider(start=1, end=10, step=1, value=max_depth, title="Depth")
depth_slider.on_change('value', update_depth)


treemap = figure(width=1000, height=800, tooltips="@name", toolbar_location=None,
           x_axis_location=None, y_axis_location=None)
treemap.x_range.range_padding = treemap.y_range.range_padding = 0
treemap.grid.grid_line_color = None

treemap.block('x', 'y', 'dx', 'dy', source=datasource, line_width=1, line_color="white",
        fill_alpha=0.8)#, fill_color=factor_cmap("name", "MediumContrast4", datasource))

# treemap.text('x', 'y', x_offset=2, text="name", source=datasource,
#        text_font_size="12pt", text_color="white")


layout = layout([
    [depth_slider],
    [file_input],
    [treemap]
])

curdoc().add_root(layout)

