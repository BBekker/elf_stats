from __future__ import print_function
import sys
from elftools.elf.elffile import ELFFile
from elftools.dwarf.compileunit import CompileUnit
from elftools.dwarf.die import AttributeValue

from dataclasses import dataclass
import leb128

# Global variable for pointer size
POINTER_SIZE = None
ENDIANNESS = "little"


@dataclass
class Die:
    tag: str
    die_offset: int


@dataclass
class Type(Die):
    name: str
    size: int


@dataclass
class Struct(Type):
    members: list["Variable"]


@dataclass
class Array(Type):
    array_size: int
    array_elements: "Type"


@dataclass
class Variable(Die):
    name: str
    location: int
    type: Type


def get_type_size(die):
    if "DW_AT_byte_size" in die.attributes:
        return die.attributes["DW_AT_byte_size"].value

    if die.tag == "DW_TAG_array_type":
        element_type = die.get_DIE_from_attribute("DW_AT_type")
        element_size = get_type_size(element_type)
        return element_size * get_array_count(die)

    if die.tag in ["DW_TAG_typedef", "DW_TAG_const_type", "DW_TAG_volatile_type"]:
        if "DW_AT_type" in die.attributes:
            typedef_die = die.get_DIE_from_attribute("DW_AT_type")
            return get_type_size(typedef_die)

    if die.tag == "DW_TAG_base_type":
        if "DW_AT_byte_size" in die.attributes:
            byte_size = die.attributes["DW_AT_byte_size"].value
            return byte_size

    if die.tag == "DW_TAG_pointer_type":
        return POINTER_SIZE

    # For structures, we might need to calculate the size based on members
    if die.tag == "DW_TAG_structure_type":
        max_offset = 0
        max_size = 0
        for member in die.iter_children():
            if member.tag == "DW_TAG_member" and "DW_AT_data_member_location" in member.attributes:
                offset = member.attributes["DW_AT_data_member_location"].value
                member_type = member.get_DIE_from_attribute("DW_AT_type")
                member_size = get_type_size(member_type)
                max_offset = max(max_offset, offset)
                max_size = max(max_size, member_size)
        return max_offset + max_size

    return None


def get_die_name(die):
    if die.tag == "DW_TAG_base_type":
        return die.attributes["DW_AT_name"].value.decode("utf-8")

    elif die.tag == "DW_TAG_typedef":
        if "DW_AT_name" in die.attributes:
            return die.attributes["DW_AT_name"].value.decode("utf-8")
        elif "DW_AT_type" in die.attributes:
            return get_die_name(die.get_DIE_from_attribute("DW_AT_type"))
        else:
            return "Unnamed typedef"

    elif die.tag == "DW_TAG_member":
        if "DW_AT_name" in die.attributes:
            return die.attributes["DW_AT_name"].value.decode("utf-8")
        elif "DW_AT_type" in die.attributes:
            return "Unnamed " + get_die_name(die.get_DIE_from_attribute("DW_AT_type"))
        else:
            return "Unnamed member"

    elif die.tag == "DW_TAG_variable":
        if "DW_AT_name" in die.attributes:
            return die.attributes["DW_AT_name"].value.decode("utf-8")
        else:
            return "Unnamed variable"

    elif die.tag == "DW_TAG_pointer_type":
        if "DW_AT_type" in die.attributes:
            pointed_type = get_die_name(die.get_DIE_from_attribute("DW_AT_type"))
            return f"{pointed_type}*"
        else:
            return "void*"

    elif die.tag == "DW_TAG_array_type":
        if "DW_AT_type" in die.attributes:
            element_type = get_die_name(die.get_DIE_from_attribute("DW_AT_type"))
            array_size = get_array_count(die)
            return f"{element_type}[{array_size}]"

    elif die.tag == "DW_TAG_const_type":
        if "DW_AT_type" in die.attributes:
            return "const " + get_die_name(die.get_DIE_from_attribute("DW_AT_type"))
        else:
            return "const"

    elif die.tag == "DW_TAG_volatile_type":
        if "DW_AT_type" in die.attributes:
            return "volatile " + get_die_name(die.get_DIE_from_attribute("DW_AT_type"))
        else:
            return "volatile"

    elif die.tag == "DW_TAG_structure_type":
        if "DW_AT_name" in die.attributes:
            return die.attributes["DW_AT_name"].value.decode("utf-8")
        else:
            return "unnamed struct"

    elif die.tag == "DW_TAG_union_type":
        if "DW_AT_name" in die.attributes:
            return die.attributes["DW_AT_name"].value.decode("utf-8")
        else:
            return "unnamed union"

    else:
        return f"unhandled type ({die.tag})"


def get_array_count(die):
    for child in die.iter_children():
        if child.tag == "DW_TAG_subrange_type":
            if "DW_AT_count" in child.attributes:
                return child.attributes["DW_AT_count"].value
            elif "DW_AT_upper_bound" in child.attributes:
                return child.attributes["DW_AT_upper_bound"].value + 1
            else:
                print("Array with 0 size")
                return 0
    assert False, "Not a proper array type"


def parse_type(die):
    if die.tag == "DW_TAG_structure_type" or die.tag == "DW_TAG_union_type":
        structure = Struct(
            tag=die.tag,
            die_offset=die.offset,
            name=get_die_name(die),
            members=[],
            size=get_type_size(die),
        )
        for child in die.iter_children():
            if child.tag == "DW_TAG_member":
                structure.members.append(parse_variable(child))
            else:
                print(f"unhandled child tag: {child.tag}")
        return structure

    if die.tag == "DW_TAG_array_type":
        structure = Array(
            tag=die.tag,
            die_offset=die.offset,
            name=get_die_name(die),
            size=get_type_size(die),
            array_size=get_array_count(die),
            array_elements=parse_type(die.get_DIE_from_attribute("DW_AT_type")),
        )
        return structure

    if die.tag in ["DW_TAG_typedef", "DW_TAG_const_type", "DW_TAG_volatile_type"]:
        type = parse_type(die.get_DIE_from_attribute("DW_AT_type"))
        if type:
            type.name = get_die_name(die)
        return type

    if die.tag in ["DW_TAG_base_type", "DW_TAG_pointer_type"]:
        return Type(
            tag=die.tag,
            die_offset=die.offset,
            name=get_die_name(die),
            size=get_type_size(die),
        )

    return Type(
        tag=die.tag,
        die_offset=die.offset,
        name=get_die_name(die),
        size=get_type_size(die),
    )


def get_structures(CU):
    structures = []
    for die in CU.iter_DIEs():
        element = parse_type(die)
        if element:
            structures.append(element)
    return structures


def decode_attribute_value(attr: AttributeValue):
    if attr.form == "DW_FORM_exprloc":
        loc_length = leb128.u.decode([attr.value[0]])  # this is a bit of a hack, but this leb128 library is broken
        return int.from_bytes(attr.value[1 : (1 + loc_length)], ENDIANNESS)
    elif attr.form.startswith("DW_FORM_data"):
        return attr.value  # decoded by the library it seems
    elif attr.form == "DW_FORM_block1":
        length = int.from_bytes(attr.value[:1], ENDIANNESS)
        return int.from_bytes(
            attr.value[1:][: length + 1], ENDIANNESS
        )  # +1 Not sure if this is a bug in gcc or the dwarf spec?
    elif attr.form == "DW_FORM_block2":
        length = int.from_bytes(attr.value[:2], ENDIANNESS)
        return int.from_bytes(attr.value[2:][: length + 1], ENDIANNESS)
    elif attr.form == "DW_FORM_block4":
        length = int.from_bytes(attr.value[:4], ENDIANNESS)
        return int.from_bytes(attr.value[4:][: length + 1], ENDIANNESS)
    else:
        assert False, "Data form not parsed"


def parse_variable(die):
    if "DW_AT_type" in die.attributes:
        type_die = die.get_DIE_from_attribute("DW_AT_type")
    elif "DW_AT_abstract_origin" in die.attributes:
        type_die = die.get_DIE_from_attribute("DW_AT_abstract_origin")
    else:
        print("Skipping die:")
        print(die)
        return None

    if "DW_AT_location" in die.attributes:
        location = decode_attribute_value(die.attributes["DW_AT_location"])
    elif "DW_AT_data_member_location" in die.attributes:
        location = decode_attribute_value(die.attributes["DW_AT_data_member_location"])
    else:
        location = 0

    return Variable(
        name=get_die_name(die),
        type=parse_type(type_die),
        location=location,
        die_offset=die.offset,
        tag=die.tag,
    )


def get_variables(CU: CompileUnit, memrange=(0, 0xFFFFFFFF)):
    variables = []
    for die in CU.iter_DIEs():
        if die.tag == "DW_TAG_variable":
            v = parse_variable(die)
            if v and v.location >= memrange[0] and v.location <= memrange[1]:
                variables.append(v)
    return variables


def process_elffile(elffile):
    if not elffile.has_dwarf_info():
        print("  file has no DWARF info")
        return

    global POINTER_SIZE, ENDIANNESS
    POINTER_SIZE = 8 if elffile.elfclass == 64 else 4
    ENDIANNESS = "little" if elffile.little_endian else "big"

    dwarfinfo = elffile.get_dwarf_info()

    cus = dwarfinfo.iter_CUs()
    variables = []
    for CU in cus:
        print(
            "  Found a compile unit at offset %s, length %s, name %s"
            % (CU.cu_offset, CU["unit_length"], CU.get_top_DIE().get_full_path())
        )

        # structures = get_structures(CU, dwarfinfo)

        # for structure in structures:
        #     pprint.pprint(structure)

        variables += get_variables(CU)
        # for variable in variables:
        #    pprint.pprint(variable)
    return variables


def process_file(filename):
    global POINTER_SIZE
    print("Processing file:", filename)
    with open(filename, "rb") as f:
        elffile = ELFFile(f)
        process_elffile(elffile)


if __name__ == "__main__":
    if sys.argv[1] == "--test":
        for filename in sys.argv[2:]:
            process_file(filename)
