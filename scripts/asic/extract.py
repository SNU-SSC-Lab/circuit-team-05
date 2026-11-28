"""KLayout batch extraction of ordinary NSPL 5 V CMOS core devices.

Environment: SSC_GDS, SSC_TOP, SSC_SPICE. GPIO/ESD/analog devices are not
qualified by this core extractor. Layer numbers come from the kit's layermap.
"""
import json
import os
from pathlib import Path

import pya


def main():
    source = pya.Layout()
    source.read(os.environ['SSC_GDS'])
    name = os.environ['SSC_TOP']
    original = source.cell(name)
    if original is None or original.is_empty():
        raise ValueError('missing or empty GDS top: '+name)
    # Flatten shapes, retaining only top-level labels. Leaf pin labels must
    # not accidentally become thousands of chip ports or join unrelated nets.
    layout = pya.Layout()
    layout.dbu = source.dbu
    cell = layout.create_cell(name)
    for li in source.layer_indices():
        lo = layout.layer(source.get_info(li))
        cell.shapes(lo).insert(pya.Region(original.begin_shapes_rec(li)))
        for shape in original.shapes(li).each():
            if shape.is_text():
                cell.shapes(lo).insert(shape.text)
    l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(layout, cell, []))

    def polygon(number, label):
        return l2n.make_polygon_layer(layout.layer(number, 0), label)

    nwell = polygon(2, 'nwell')
    active = polygon(11, 'active')
    poly = polygon(12, 'poly')
    nplus = polygon(14, 'nplus')
    pplus = polygon(15, 'pplus')
    contact = polygon(31, 'contact')
    m1, v1 = polygon(32, 'metal1'), polygon(33, 'via1')
    m2, v2 = polygon(34, 'metal2'), polygon(35, 'via2')
    m3 = polygon(36, 'metal3')
    bulk = l2n.make_layer('bulk')
    pactive, nactive = active & nwell & pplus, (active - nwell) & nplus
    ntie, ptie = active & nwell & nplus, (active - nwell) & pplus
    pgate, ngate = pactive & poly, nactive & poly
    psd, nsd = pactive - poly, nactive - poly
    for model, sd, gate, well in [('pmos4', psd, pgate, nwell), ('nmos4', nsd, ngate, bulk)]:
        l2n.extract_devices(pya.DeviceExtractorMOS4Transistor(model),
                            {'SD': sd, 'G': gate, 'P': poly, 'W': well})
    for layer in [psd, nsd, poly, contact, m1, v1, m2, v2, m3, nwell, ntie, ptie]:
        l2n.connect(layer)
    for first, second in [(psd, contact), (nsd, contact), (poly, contact),
                          (ntie, contact), (ptie, contact), (nwell, ntie),
                          (contact, m1), (m1, v1), (v1, m2), (m2, v2), (v2, m3)]:
        l2n.connect(first, second)
    for metal, number in [(poly, 41), (m1, 42), (m2, 44), (m3, 46)]:
        labels = l2n.make_text_layer(layout.layer(number, 0), 'labels'+str(number))
        l2n.connect(metal, labels)
    l2n.connect_global(bulk, 'VSS')
    l2n.connect_global(ptie, 'VSS')
    l2n.extract_netlist()
    netlist = l2n.netlist()
    netlist.make_top_level_pins()
    netlist.combine_devices()
    netlist.purge()
    circuit = netlist.circuit_by_name(name)
    if circuit is None or not list(circuit.each_device()):
        raise ValueError('no extracted devices')
    output = Path(os.environ['SSC_SPICE'])
    writer = pya.NetlistSpiceWriter()
    writer.use_net_names = True
    netlist.write(str(output), writer)
    summary = {'top': name, 'devices': len(list(circuit.each_device())),
               'pins': [p.name() for p in circuit.each_pin()],
               'scope': 'ordinary 5 V CMOS core; substrate VSS; GPIO/ESD not qualified'}
    output.with_suffix('.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))


if os.environ.get('SSC_TOPS'):
    folder = Path(os.environ['SSC_SPICE_DIR'])
    folder.mkdir(parents=True, exist_ok=True)
    for item in os.environ['SSC_TOPS'].split(','):
        os.environ['SSC_TOP'] = item
        os.environ['SSC_SPICE'] = str(folder/(item+'.spice'))
        main()
else:
    main()
