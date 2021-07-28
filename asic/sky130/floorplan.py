import math

def setup_floorplan(fp, chip):
    f, _, _, _, _ = make_floorplan(fp)
    return f

def make_floorplan(fp):
    # TODO: this should be automatically set to a valid value
    fp.db_units = 1000

    # Extract important tech-specific values
    std_cell_w = fp.std_cell_width
    std_cell_h = fp.std_cell_height

    # gpio cell is tallest in Sky130 io lib (should we validate this?)
    gpio_cell_w = fp.available_cells['gpio'].width
    gpio_cell_h = fp.available_cells['gpio'].height
    pow_cell_h = fp.available_cells['vdd'].height
    corner_w = fp.available_cells['corner'].width
    corner_h = fp.available_cells['corner'].height
    max_io_cell_h = max(gpio_cell_h, pow_cell_h, corner_w, corner_h)

    # Initialize die
    margin = math.ceil(4 * max_io_cell_h)
    
    die_w = 6800 * std_cell_w + 2 * margin
    die_h = 900 * std_cell_h + 2 * margin

    # necessary to fulfill these conditions to be able to fill padring 
    assert die_w % 1 == 0
    assert die_h % 1 == 0

    ram_core_space = 250 * std_cell_w

    ram_w = fp.available_cells['ram'].width
    ram_h = fp.available_cells['ram'].height
    ram_x = fp.snap(die_w - margin - ram_w - ram_core_space, std_cell_w)
    ram_y = fp.snap(die_h - margin - ram_h - 50 * std_cell_h, std_cell_h)

    fp.create_die_area(die_w, die_h,
        core_area=(margin, margin, ram_x - ram_core_space, die_h - margin))

    # Place RAM
    # Must be placed outside core area to ensure we don't run into routing
    # congestion issues (due to cells being placed too close to RAM pins)
    fp.place_macros([('soc.ram.u_mem.gen_sky130.u_impl_sky130.mem', 'ram')], ram_x, ram_y, 0, 0, 'N')

    # Define pads and associated pins
    gpio_w = [(f'padring.we_pads\\[0\\].i0.padio\\[{i}\\].i0.gpio', f'we_pad[{i}]', 'gpio') for i in range(9)]
    gpio_n = [(f'padring.no_pads\\[0\\].i0.padio\\[{i}\\].i0.gpio', f'no_pad[{i}]', 'gpio') for i in range(9)]
    gpio_s = [(f'padring.so_pads\\[0\\].i0.padio\\[{i}\\].i0.gpio', f'so_pad[{i}]', 'gpio') for i in range(9)]
    gpio_e = [(f'padring.ea_pads\\[0\\].i0.padio\\[{i}\\].i0.gpio', f'ea_pad[{i}]', 'gpio') for i in range(9)]
    power = [[(f'padring.{side}_pads\\[0\\].i0.pad{port}\\[0\\].i0.io{port}',
               f'{port}' if port in ('vdd', 'vss') else f'{side}_{port}',
               f'{port}')
                for port in ('vdd', 'vss', 'vddio', 'vssio')]
                for side in ('we', 'no', 'ea', 'so')]

    pads_w = gpio_w[:5] + power[0] + gpio_w[5:9]
    pads_n = gpio_n[:5] + power[1] + gpio_n[5:9]
    pads_e = gpio_e[:5] + power[2] + gpio_e[5:9]
    pads_s = gpio_s[:5] + power[3] + gpio_s[5:9]

    # Place pads and pins w/ equal spacing
    # TODO: place pins directly under pad metal area
    die_w, die_h = fp.die_area

    pin_depth_offset = 60
    pin_size = 10

    # Place corners
    # NOTE: scalar placement functions could be nice
    fp.place_macros([('corner_sw/corner', 'corner')], 0, 0, 0, 0, 'S')
    fp.place_macros([('corner_nw/corner', 'corner')], 0, die_h - corner_w, 0, 0, 'W')
    fp.place_macros([('corner_se/corner', 'corner')], die_w - corner_h, 0, 0, 0, 'E')
    fp.place_macros([('corner_ne/corner', 'corner')], die_w - corner_w, die_h - corner_h, 0, 0, 'N')
    
    fill_cell_h = fp.available_cells['fill1'].height

    # west
    pads_width = sum(fp.available_cells[cell].width for _, _, cell in pads_w)
    spacing = fp.snap((die_h - corner_w - corner_h - pads_width) / (len(pads_w) + 1), 1)

    y = corner_h + spacing
    for pad_name, pin_name, pad_type in pads_w:
        width = fp.available_cells[pad_type].width
        height = fp.available_cells[pad_type].height

        fp.place_macros([(pad_name, pad_type)], 0, y, 0, 0, 'W')
        # fp.place_pin([pin_name], 0, y, 0, 0, 10, 10, 'm5', 'N')

        y += width + spacing

    fp.fill_io_region([(0, 0), (fill_cell_h, die_h)], ['fill1', 'fill5', 'fill10', 'fill20'], 'W')

    # north
    pads_width = sum(fp.available_cells[cell].width for _, _, cell in pads_n)
    spacing = fp.snap((die_w - corner_w - corner_h - pads_width) / (len(pads_n) + 1), 1)

    x = corner_h + spacing
    for pad_name, pin_name, pad_type in pads_n:
        width = fp.available_cells[pad_type].width
        height = fp.available_cells[pad_type].height

        fp.place_macros([(pad_name, pad_type)], x, die_h - height, 0, 0, 'N')
        # fp.place_pin([pin_name], x + width/2, die_h - pin_depth_offset, 0, 0, pin_size, pin_size, 'm5', 'N')

        x += width + spacing

    fp.fill_io_region([(0, die_h - fill_cell_h), (die_w, die_h)], ['fill1', 'fill5', 'fill10', 'fill20'], 'N')

    # east
    pads_width = sum(fp.available_cells[cell].width for _, _, cell in pads_e)
    spacing = fp.snap((die_h - corner_w - corner_h - pads_width) / (len(pads_e) + 1), 1)
    y = corner_w + spacing
    for pad_name, pin_name, pad_type in pads_e:
        width = fp.available_cells[pad_type].width
        height = fp.available_cells[pad_type].height

        fp.place_macros([(pad_name, pad_type)], die_w - height, y, 0, 0, 'E')

        y += width + spacing

    fp.fill_io_region([(die_w - fill_cell_h, 0), (die_w, die_h)], ['fill1', 'fill5', 'fill10', 'fill20'], 'E')

    # south
    pads_width = sum(fp.available_cells[cell].width for _, _, cell in pads_s)
    spacing = fp.snap((die_w - corner_w - corner_h - pads_width) / (len(pads_s) + 1), 1)

    x = corner_w + spacing
    for pad_name, pin_name, pad_type in pads_s:
        width = fp.available_cells[pad_type].width
        height = fp.available_cells[pad_type].height

        fp.place_macros([(pad_name, pad_type)], x, 0, 0, 0, 'S')
        # fp.place_pin([pin_name], x + width/2, pin_depth_offset, 0, 0, pin_size, pin_size, 'm5', 'N')

        x += width + spacing

    fp.fill_io_region([(0, 0), (die_w, fill_cell_h)], ['fill1', 'fill5', 'fill10', 'fill20'], 'S')
    
    fill_1_name = fp.available_cells['fill1'].tech_name
    fill_5_name = fp.available_cells['fill5'].tech_name
    fill_10_name = fp.available_cells['fill10'].tech_name
    fill_20_name = fp.available_cells['fill20'].tech_name
    fill_1_count = len([m for m in fp.macros if m['cell'] == fill_1_name])
    fill_5_count = len([m for m in fp.macros if m['cell'] == fill_5_name])
    fill_10_count = len([m for m in fp.macros if m['cell'] == fill_10_name])
    fill_20_count = len([m for m in fp.macros if m['cell'] == fill_20_name])

    return fp, fill_1_count, fill_5_count, fill_10_count, fill_20_count
