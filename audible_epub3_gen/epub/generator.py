import xml.etree.ElementTree as ET

def generate_smil(file_name, audio_file, par_list, output_path):
    smil = ET.Element('smil', attrib={'xmlns': 'http://www.w3.org/ns/SMIL', 'version': '3.0'})
    body = ET.SubElement(smil, 'body')
    seq = ET.SubElement(body, 'seq')

    for par in par_list:
        par_el = ET.SubElement(seq, 'par')
        ET.SubElement(par_el, 'text', {'src': f"{file_name}#{par['id']}"})
        ET.SubElement(par_el, 'audio', {
            'src': audio_file,
            'clipBegin': f"{par['clipBegin']}s",
            'clipEnd': f"{par['clipEnd']}s"
        })

    tree = ET.ElementTree(smil)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"SMIL saved to {output_path}")
