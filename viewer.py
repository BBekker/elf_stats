from squarify import normalize_sizes, squarify

from bokeh.plotting import figure, ColumnDataSource
from bokeh.transform import factor_cmap
from bokeh.layouts import layout
import parser

from bokeh.io import curdoc
from bokeh.models.widgets import FileInput, Slider, Div
from pybase64 import b64decode
import io

border = 1.0

square_size = {"x": 0, "y": 0, "dx": 1000, "dy": 800}
variables = []
treemap_data = []

datasource = ColumnDataSource({"x": [], "y": [], "dx": [], "dy": [], "name": [], "size": []})

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
        square["x"] += border
        square["y"] += border
        square["dx"] -= 2*border
        square["dy"] -= 2*border
        add_if_leaf(node, max_depth - 1, square, node.name)

    #transpose to column data
    column_data = {"x": [], "y": [], "dx": [], "dy": [], "name": []}
    column_data["x"] = [x["x"] for x in treemap_data]
    column_data["y"] = [x["y"] for x in treemap_data]
    column_data["dx"] = [x["dx"] for x in treemap_data]
    column_data["dy"] = [x["dy"] for x in treemap_data]
    column_data["name"] = [x["name"] for x in treemap_data]
    column_data["size"] = [x["size"] for x in treemap_data]
    datasource.data = column_data




def add_if_leaf(node: parser.Variable, depth: int, input_square: dict[int, int, int, int], path_name: str):
    """
       if max depth is 0, or we are at a leaf node, add a square for this node.
       else, loop through children
       - calculate a square for each child and call function recursively
    """
    if depth == 0 or (not isinstance(node.type, parser.Struct) and not isinstance(node.type, parser.Array)) :
        treemap_data.append({"name": node.type.name+" "+path_name, **input_square, "size": node.type.size})
    else:
        if isinstance(node.type, parser.Struct):
            children: list[parser.Variable] = node.type.members
            children.sort(key=lambda x: x.type.size, reverse=True)
            if node.type.tag == "DW_TAG_union_type":
                #Only return one item for unions
                children = [children[0]] 
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
    

def build_overview_text_recursive(variable):
    html = "<li>"
    #print("parsing", variable, flush=True)
    html += f"0x{variable.location:08x} {variable.type.name} {variable.name}, size: {variable.type.size} bytes"
    if isinstance(variable.type, parser.Struct):
        html += "<ul>"
        for member in variable.type.members:
            html += build_overview_text_recursive(member)
        html += "</ul>"

    if isinstance(variable.type, parser.Array):
        html += "<ul>"
        fake_members = [parser.Variable(tag="", die_offset=0, name=f"[{i}]", location=i*variable.type.array_elements.size, type=variable.type.array_elements) for i in range(variable.type.array_size)]
        for member in fake_members:
            html += build_overview_text_recursive(member)
        html += "</ul>"

    html += "</li>"
    return html

def build_overview_text():
    html = "<ul>"
    for variable in variables:
        html += build_overview_text_recursive(variable)
    html += "</ul>"
    return html
        




def upload_elf(attr, old, new):
    global status_text
    status_text.text = "Decoding"

    decoded = b64decode(new)
    f = io.BytesIO(decoded)

    status_text.text = "Parsing"
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
    
    status_text.text = "Building map"
    generate_treemap_data()
    status_text.text = "Done"

    overview.text = build_overview_text()

def update_depth(attr, old, new):
    global status_text
    status_text.text = "Building map"
    global max_depth
    max_depth = new
    generate_treemap_data()
    status_text.text = "Done"
    

file_input = FileInput(accept=".elf, .axf")
file_input.on_change('value', upload_elf)

depth_slider = Slider(start=1, end=10, step=1, value=max_depth, title="Depth")
depth_slider.on_change('value', update_depth)


treemap = figure(width=1000, height=800, tooltips="@name, @size bytes", toolbar_location=None,
           x_axis_location=None, y_axis_location=None)
treemap.x_range.range_padding = treemap.y_range.range_padding = 0
treemap.grid.grid_line_color = None

treemap.block('x', 'y', 'dx', 'dy', source=datasource, line_width=1, line_color="white",
        fill_alpha=0.8)#, fill_color=factor_cmap("name", "MediumContrast4", datasource))

# treemap.text('x', 'y', x_offset=2, text="name", source=datasource,
#        text_font_size="12pt", text_color="white")

status_text = Div(text="pick a file")

overview = Div(text="pick a file")

layout = layout([
    [depth_slider],
    [file_input],
    [status_text],
    [treemap],
    [overview]
])

curdoc().add_root(layout)

