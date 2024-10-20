from __future__ import print_function
from collections import defaultdict
import os
import sys
import posixpath
import pprint

# If pyelftools is not installed, the example can also run from the root or
# examples/ dir of the source distribution.
sys.path[0:0] = ['.', '..']

from elftools.elf.elffile import ELFFile
from elftools.dwarf import compileunit
from elftools.dwarf.die import DIE
import elftools.common.exceptions

# Global variable for pointer size
POINTER_SIZE = None

def get_type_size(die, dwarfinfo):
    if 'DW_AT_byte_size' in die.attributes:
        return die.attributes['DW_AT_byte_size'].value

    if die.tag == 'DW_TAG_array_type':
        element_type = die.get_DIE_from_attribute('DW_AT_type')
        element_size = get_type_size(element_type, dwarfinfo)
        for child in die.iter_children():
            if child.tag == 'DW_TAG_subrange_type':
                if 'DW_AT_count' in child.attributes:
                    return element_size * child.attributes['DW_AT_count'].value
                elif 'DW_AT_upper_bound' in child.attributes:
                    return element_size * (child.attributes['DW_AT_upper_bound'].value + 1)

    if die.tag == 'DW_TAG_typedef' or die.tag == 'DW_TAG_const_type' or die.tag == 'DW_TAG_volatile_type':
        if 'DW_AT_type' in die.attributes:
            typedef_die = die.get_DIE_from_attribute('DW_AT_type')
            return get_type_size(typedef_die, dwarfinfo)

    if die.tag == 'DW_TAG_base_type':
        if 'DW_AT_encoding' in die.attributes and 'DW_AT_byte_size' in die.attributes:
            encoding = die.attributes['DW_AT_encoding'].value
            byte_size = die.attributes['DW_AT_byte_size'].value
            return byte_size

    if die.tag == 'DW_TAG_pointer_type':
        return POINTER_SIZE

    # For structures, we might need to calculate the size based on members
    if die.tag == 'DW_TAG_structure_type':
        max_offset = 0
        max_size = 0
        for member in die.iter_children():
            if member.tag == 'DW_TAG_member' and 'DW_AT_data_member_location' in member.attributes:
                offset = member.attributes['DW_AT_data_member_location'].value
                member_type = member.get_DIE_from_attribute('DW_AT_type')
                member_size = get_type_size(member_type, dwarfinfo)
                max_offset = max(max_offset, offset)
                max_size = max(max_size, member_size)
        return max_offset + max_size

    return None

def get_type_name(die, dwarfinfo):
    if die.tag == 'DW_TAG_base_type':
        return die.attributes['DW_AT_name'].value.decode('utf-8')
    elif die.tag == 'DW_TAG_typedef':
        if 'DW_AT_type' in die.attributes:
            return get_type_name(die.get_DIE_from_attribute('DW_AT_type'), dwarfinfo)
        else:
            return die.attributes['DW_AT_name'].value.decode('utf-8')
    elif die.tag == 'DW_TAG_pointer_type':
        if 'DW_AT_type' in die.attributes:
            pointed_type = get_type_name(die.get_DIE_from_attribute('DW_AT_type'), dwarfinfo)
            return f"{pointed_type}*"
        else:
            return "void*"
    elif die.tag == 'DW_TAG_array_type':
        if 'DW_AT_type' in die.attributes:
            element_type = get_type_name(die.get_DIE_from_attribute('DW_AT_type'), dwarfinfo)
            array_size = get_array_size(die)
            return f"{element_type}[{array_size}]"
    elif die.tag == 'DW_TAG_structure_type':
        if 'DW_AT_name' in die.attributes:
            return die.attributes['DW_AT_name'].value.decode('utf-8')
        else:
            return "unnamed structure"
    else:
        return f"unhandled type ({die.tag})"

def get_array_size(die):
    for child in die.iter_children():
        if child.tag == 'DW_TAG_subrange_type':
            if 'DW_AT_count' in child.attributes:
                return child.attributes['DW_AT_count'].value
            elif 'DW_AT_upper_bound' in child.attributes:
                return child.attributes['DW_AT_upper_bound'].value + 1
    return None

def get_structure_by_offset(structures, offset):
    for structure in structures:
        if structure['die_offset'] == offset:
            return structure
    return None


def parse_type(die, dwarfinfo):
    if die.tag == "DW_TAG_structure_type":
        structure = {
            "name": die.attributes.get('DW_AT_name', {}).value,
            "members": [],
            "die_offset": die.offset,
            "size": get_type_size(die, dwarfinfo)
        }
        for child in die.iter_children():
            if child.tag == "DW_TAG_member":
                member = {
                    "name": child.attributes['DW_AT_name'].value.decode('utf-8'),
                    "offset": child.attributes.get('DW_AT_data_member_location', {}).value,
                    "type": parse_type(child.get_DIE_from_attribute('DW_AT_type'), dwarfinfo),
                }
                structure["members"].append(member)
        return structure
    
         # Handle array types
    if die.tag == 'DW_TAG_array_type':
        structure = {
            "name": get_type_name(die, dwarfinfo),
            "die_offset": die.offset,
            "size": get_type_size(die, dwarfinfo)
        }
        element_type_die = die.get_DIE_from_attribute('DW_AT_type')
        array_size = get_array_size(die)
        if array_size:
            structure["array_size"] = array_size
            structure["array_elements"] = parse_type(element_type_die, dwarfinfo)
            # Calculate total size of the array
            element_size = get_type_size(element_type_die, dwarfinfo)
            if element_size:
                structure["size"] = element_size * array_size
        return structure
    
    if die.tag in ['DW_TAG_base_type', 'DW_TAG_pointer_type', 'DW_TAG_typedef'] :
        return {
            "name": get_type_name(die, dwarfinfo),
            "die_offset": die.offset,
            "size": get_type_size(die, dwarfinfo)
        }


def get_structures(CU, dwarfinfo):
    structures = []
    for die in CU.iter_DIEs():
        element = parse_type(die, dwarfinfo)
        if element:
            structures.append(element)
    return structures

def parse_variable(die, dwarfinfo):
    print(die)
    return {
        "name": die.attributes['DW_AT_name'].value.decode('utf-8'),
        "type": parse_type(die.get_DIE_from_attribute('DW_AT_type'), dwarfinfo),
        "location": hex(int.from_bytes(die.attributes['DW_AT_location'].value, byteorder='little'))
    }

def get_variables(CU, dwarfinfo):
    variables = []
    for die in CU.iter_DIEs():
        if die.tag == 'DW_TAG_variable':
            variables.append(parse_variable(die, dwarfinfo))
    return variables


def process_file(filename):
    global POINTER_SIZE
    print('Processing file:', filename)
    with open(filename, 'rb') as f:
        elffile = ELFFile(f)

        if not elffile.has_dwarf_info():
            print('  file has no DWARF info')
            return

        POINTER_SIZE = 8 if elffile.elfclass == 64 else 4
        dwarfinfo = elffile.get_dwarf_info()
        cus = dwarfinfo.iter_CUs()
        for CU in cus:
            print('  Found a compile unit at offset %s, length %s, name %s' % (
                CU.cu_offset, CU['unit_length'], CU.get_top_DIE().get_full_path()))
            
            # structures = get_structures(CU, dwarfinfo)

            # for structure in structures:
            #     pprint.pprint(structure)

            variables = get_variables(CU, dwarfinfo)
            for variable in variables:
                pprint.pprint(variable)
        print('Done processing', filename)
        return

if __name__ == '__main__':
    if sys.argv[1] == '--test':
        for filename in sys.argv[2:]:
            process_file(filename)
