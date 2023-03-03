#!/usr/bin/env python3

import siliconcompiler

import argparse
import os
import sys

# Libraries
from siliconcompiler.libs import sky130io
import libs.sky130sram

from floorplan import generate_core_floorplan, generate_top_floorplan

ASIC_CORE_CFG = 'asic_core.pkg.json'


def configure_remote(chip):
    chip.set('option', 'remote', True)

    for library in chip.getkeys('library'):
        for fileset in chip.getkeys('library', library, 'output'):
            for filetype in chip.getkeys('library', library, 'output', fileset):
                # Need to copy library files into build directory for remote run so the
                # server can access them
                chip.hash_files('library', library, 'output', fileset, filetype)
                chip.set('library', library, 'output', fileset, filetype, True, field='copy')


def add_sources_core(chip):
    chip.add('option', 'define', 'SYNTHESIS')

    # Include dirs
    chip.add('option', 'idir', 'opentitan/hw/ip/prim/rtl')
    chip.add('option', 'idir', 'opentitan/hw/dv/sv/dv_utils')

    # Add RTL of all modules we use to search path
    chip.add('option', 'ydir', 'hw/prim')
    chip.add('option', 'ydir', 'opentitan/hw/ip/tlul/rtl')
    chip.add('option', 'ydir', 'opentitan/hw/ip/rv_core_ibex/rtl')
    chip.add('option', 'ydir', 'opentitan/hw/vendor/lowrisc_ibex/rtl')
    chip.add('option', 'ydir', 'opentitan/hw/ip/uart/rtl')
    chip.add('option', 'ydir', 'opentitan/hw/ip/gpio/rtl')
    chip.add('option', 'ydir', 'opentitan/hw/ip/prim/rtl')
    chip.add('option', 'ydir', 'opentitan/hw/ip/prim_generic/rtl')

    # SV packages (need to be added explicitly)
    chip.input('opentitan/hw/ip/prim/rtl/prim_util_pkg.sv')
    chip.input('opentitan/hw/ip/prim/rtl/prim_secded_pkg.sv')
    chip.input('opentitan/hw/top_earlgrey/rtl/top_pkg.sv')
    chip.input('opentitan/hw/ip/tlul/rtl/tlul_pkg.sv')
    chip.input('hw/xbar_pkg.sv')
    chip.input('opentitan/hw/vendor/lowrisc_ibex/rtl/ibex_pkg.sv')
    chip.input('opentitan/hw/ip/uart/rtl/uart_reg_pkg.sv')
    chip.input('opentitan/hw/ip/gpio/rtl/gpio_reg_pkg.sv')
    chip.input('hw/prim/prim_pkg.sv')
    chip.input('opentitan/hw/ip/lc_ctrl/rtl/lc_ctrl_pkg.sv')
    chip.input('opentitan/hw/ip/lc_ctrl/rtl/lc_ctrl_state_pkg.sv')
    chip.input('opentitan/hw/ip/prim/rtl/prim_esc_pkg.sv')
    chip.input('opentitan/hw/ip/prim/rtl/prim_ram_1p_pkg.sv')

    # Hack to work around Yosys + Surelog issue. Even though this is found in
    # one of our ydirs, we get different synthesis results if this isn't ordered
    # earlier.
    chip.input('opentitan/hw/vendor/lowrisc_ibex/rtl/ibex_compressed_decoder.sv')

    # TODO: we're overwriting the OpenTitan uart_core, so need to include this
    # module explicitly
    chip.input('hw/uart_core.sv')

    chip.input('hw/zerosoc.sv')
    chip.input('hw/xbar.sv')
    chip.input('hw/tl_dbg.sv')


def add_sources_top(chip):
    chip.input('hw/asic_top.v')
    chip.input('hw/asic_core.bb.v')
    chip.input('oh/padring/hdl/oh_padring.v')
    chip.input('oh/padring/hdl/oh_pads_domain.v')
    chip.input('oh/padring/hdl/oh_pads_corner.v')

    chip.input('asic/sky130/io/asic_iobuf.v')
    chip.input('asic/sky130/io/asic_iovdd.v')
    chip.input('asic/sky130/io/asic_iovddio.v')
    chip.input('asic/sky130/io/asic_iovss.v')
    chip.input('asic/sky130/io/asic_iovssio.v')
    chip.input('asic/sky130/io/asic_iocorner.v')

    chip.input('opentitan/hw/top_earlgrey/rtl/top_pkg.sv')

    # Dummy blackbox modules just to get synthesis to pass (these aren't
    # acutally instantiated)
    chip.input('asic/sky130/io/asic_iopoc.v')
    chip.input('asic/sky130/io/asic_iocut.v')

    chip.input('asic/sky130/io/sky130_io.blackbox.v')


def setup_options(chip):
    '''Helper to setup common options for each build.'''
    chip.set('option', 'loglevel', 'INFO')

    # Prevent us from erroring out on lint warnings during import
    chip.set('option', 'relax', True)
    chip.set('option', 'quiet', True)

    # hack to work around fact that $readmemh now runs in context of build
    # directory and can't load .mem files using relative paths
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    chip.add('option', 'define', f'MEM_ROOT={cur_dir}')


def build_fpga():
    chip = siliconcompiler.Chip('top_icebreaker')
    setup_options(chip)

    chip.set('frontend', 'systemverilog')
    chip.set('fpga', 'partname', 'ice40up5k-sg48')
    chip.load_target('fpgaflow_demo')

    add_sources_core(chip)

    chip.input('hw/top_icebreaker.v')
    chip.input('hw/prim/ice40/prim_ice40_clock_gating.v')
    chip.input('fpga/icebreaker.pcf')

    chip.add('option', 'define', 'PRIM_DEFAULT_IMPL="prim_pkg::ImplIce40"')

    run_build(chip)


def configure_core_chip(remote=False):
    chip = siliconcompiler.Chip('asic_core')

    setup_options(chip)

    chip.set('option', 'frontend', 'systemverilog')
    chip.load_target('skywater130_demo')

    chip.use(libs.sky130sram)

    chip.set('asic', 'macrolib', ['sky130sram'])

    # Ignore cells in these libraries during DRC, they violate the rules but are
    # foundry-validated
    for task in ('extspice', 'drc'):
        chip.add('tool', 'magic', 'task', task, 'var', 'exclude', 'sky130sram')
    chip.add('tool', 'netgen', 'task', 'lvs', 'var', 'exclude', 'sky130sram')

    if remote:
        configure_remote(chip)

    add_sources_core(chip)

    chip.clock(r'we_din\[5\]', period=20)

    chip.add('option', 'define', 'PRIM_DEFAULT_IMPL="prim_pkg::ImplSky130"')
    chip.add('option', 'define', 'RAM_DEPTH=512')

    chip.input('hw/asic_core.v')

    chip.input('hw/prim/sky130/prim_sky130_ram_1p.v')
    chip.input('hw/prim/sky130/prim_sky130_clock_gating.v')

    return chip


def build_core(verify=True, remote=False, resume=False, floorplan=False):
    chip = configure_core_chip(remote)
    chip.set('option', 'resume', resume)

    chip.set('tool', 'openroad', 'task', 'place', 'var', 'place_density', '0.40')
    chip.set('tool', 'openroad', 'task', 'route', 'var', 'grt_macro_extension', '0')
    chip.set('tool', 'openroad', 'task', 'export', 'var', 'write_cdl', 'false')

    chip.set('option', 'breakpoint', floorplan and not remote, step='floorplan')

    generate_core_floorplan(chip)

    run_build(chip)

    if verify:
        run_signoff(chip, 'dfm', 'export')

    # set up pointers to final outputs for integration
    # Set physical outputs
    stackup = chip.get('option', 'stackup')
    chip.set('output', stackup, 'gds', chip.find_result('gds', step='export', index='0'))
    chip.set('output', stackup, 'lef', chip.find_result('lef', step='export', index='1'))

    # Set output netlist
    chip.set('output', 'netlist', 'verilog', chip.find_result('vg', step='export', index='1'))

    # Set timing libraries
    for scenario in chip.getkeys('constraint', 'timing'):
        corner = chip.get('constraint', 'timing', scenario, 'libcorner')[0]
        lib = chip.find_result(f'{corner}.lib', step='export', index='1')
        chip.set('output', corner, 'nldm', lib)

    # Set pex outputs
    for scenario in chip.getkeys('constraint', 'timing'):
        corner = chip.get('constraint', 'timing', scenario, 'pexcorner')
        spef = chip.find_result(f'{corner}.spef', step='export', index='1')
        chip.set('output', corner, 'spef', spef)

    # Hash output files
    for fileset in chip.getkeys('output'):
        for filetype in chip.getkeys('output', fileset):
            chip.hash_files('output', fileset, filetype)

    chip.write_manifest(ASIC_CORE_CFG)

    return chip


def configure_top_chip(core_chip=None, resume=False, remote=False):
    if not core_chip:
        if not os.path.exists(ASIC_CORE_CFG):
            print(f"'{ASIC_CORE_CFG}' has not been generated.", file=sys.stderr)
            return
        core_chip = siliconcompiler.Chip('asic_core')
        core_chip.read_manifest(ASIC_CORE_CFG)

    chip = siliconcompiler.Chip('asic_top')

    setup_options(chip)
    chip.set('option', 'resume', resume)

    chip.set('option', 'frontend', 'systemverilog')
    chip.load_target('skywater130_demo')
    chip.set('option', 'flow', 'asicflow')

    chip.use(core_chip)
    chip.use(sky130io)
    chip.use(libs.sky130sram)
    chip.set('asic', 'macrolib', [core_chip.top(), 'sky130io'])

    add_sources_top(chip)

    if remote:
        configure_remote(chip)

    # Ignore cells in these libraries during DRC, they violate the rules but are
    # foundry-validated
    for task in ('extspice', 'drc'):
        chip.add('tool', 'magic', 'task', task, 'var', 'exclude', 'sky130io')
    chip.add('tool', 'netgen', 'task', 'lvs', 'var', 'exclude', 'sky130io')

    for tool in core_chip.getkeys('tool'):
        for task in core_chip.getkeys('tool', tool, 'task'):
            if core_chip.valid('tool', tool, 'task', task, 'var', 'exclude'):
                exclude = core_chip.get('tool', tool, 'task', task, 'var', 'exclude')
                chip.set('tool', tool, 'task', task, 'var', 'exclude', exclude)

    # OpenROAD settings
    chip.set('tool', 'openroad', 'task', 'place', 'var', 'dpo_enable', 'false')
    chip.set('tool', 'openroad', 'task', 'route', 'var', 'grt_macro_extension', '0')

    return chip


def build_top(core_chip=None, verify=True, resume=False, remote=False, floorplan=False):
    chip = configure_top_chip(core_chip, remote=remote, resume=resume)

    chip.set('option', 'breakpoint', floorplan and not remote, step='floorplan')

    generate_top_floorplan(chip)

    run_build(chip)
    if verify:
        run_signoff(chip, 'syn', 'export')

    return chip


def run_build(chip):
    chip.run()
    chip.summary()


def run_signoff(chip, netlist_step, layout_step):
    gds_path = chip.find_result('gds', step=layout_step)
    netlist_path = chip.find_result('vg', step=netlist_step)

    jobname = chip.get('option', 'jobname')
    chip.set('option', 'jobname', f'{jobname}_signoff')
    chip.set('option', 'flow', 'signoffflow')

    # Hack: workaround the fact that remote runs alter the steplist
    if chip.get('option', 'remote'):
        chip.set('option', 'steplist', [])

    chip.input(gds_path)
    chip.input(netlist_path)

    run_build(chip)


def test_zerosoc_build():
    chip = build_core(verify=True)

    assert chip.get('metric', 'lvs', '0', 'errors') == 0
    assert chip.get('metric', 'drc', '0', 'errors') == 0

    # check for timing errors
    assert chip.get('metric', 'route', '0', 'holdslack') >= 0
    assert chip.get('metric', 'route', '0', 'holdwns') >= 0
    assert chip.get('metric', 'route', '0', 'holdtns') >= 0
    assert chip.get('metric', 'route', '0', 'setupslack') >= 0
    assert chip.get('metric', 'route', '0', 'setupwns') >= 0
    assert chip.get('metric', 'route', '0', 'setuptns') >= 0

    chip = build_top(verify=True)

    assert chip.get('metric', 'lvs', '0', 'errors') == 0
    assert chip.get('metric', 'drc', '0', 'errors') == 0


def test_fpga_build():
    build_fpga()


def main():
    parser = argparse.ArgumentParser(description='Build ZeroSoC')
    # parser.add_argument('--fpga',
    #                     action='store_true',
    #                     default=False,
    #                     help='Build FPGA bitstream.')
    parser.add_argument('--core-only',
                        action='store_true',
                        default=False,
                        help='Only build ASIC core GDS.')
    parser.add_argument('--top-only',
                        action='store_true',
                        default=False,
                        help='Only integrate ASIC core into padring. Assumes core already built.')
    parser.add_argument('--floorplan',
                        action='store_true',
                        default=False,
                        help='Break after floorplanning.')
    parser.add_argument('--verify',
                        action='store_true',
                        default=False,
                        help="Run DRC and LVS.")
    parser.add_argument('--remote',
                        action='store_true',
                        default=False,
                        help='Run on remote server. Requires SC remote credentials.')
    parser.add_argument('--resume',
                        action='store_true',
                        default=False,
                        help='Resume previous run.')
    options = parser.parse_args()

    verify = options.verify

    if options.core_only:
        build_core(remote=options.remote,
                   verify=verify,
                   resume=options.resume,
                   floorplan=options.floorplan)
    elif options.top_only:
        build_top(verify=verify,
                  resume=options.resume,
                  floorplan=options.floorplan)
    else:
        core_chip = build_core(remote=options.remote,
                               verify=False,
                               resume=options.resume,
                               floorplan=options.floorplan)
        build_top(core_chip=core_chip,
                  remote=options.remote,
                  verify=verify,
                  resume=options.resume,
                  floorplan=options.floorplan)


if __name__ == '__main__':
    main()
