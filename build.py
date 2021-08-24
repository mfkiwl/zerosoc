import argparse
import siliconcompiler as sc
import os
import importlib
import shutil

from sources import add_sources

from asic.sky130.floorplan import core, padring

def init_chip(jobid=0):
    chip = sc.Chip()

    # Prevent us from erroring out on lint warnings during import
    chip.set('relax', 'true')

    # hack to work around fact that $readmemh now runs in context of build
    # directory and can't load .mem files using relative paths
    cur_dir = os.path.dirname(os.path.realpath(__file__))
    chip.add('define', f'MEM_ROOT={cur_dir}')

    if jobid is not None:
        chip.set('jobid', jobid)

    return chip

def configure_svflow(chip, start=None, stop=None):
    flowpipe = [('import', 'morty', 'open'),
                ('convert', 'sv2v', None),
                ('syn', 'yosys', 'yosys'),
                ('synopt', 'openroad', 'openroad'),
                ('floorplan', 'openroad', 'openroad'),
                ('place', 'openroad', 'openroad'),
                ('cts', 'openroad', 'openroad'),
                ('route', 'openroad', 'openroad'),
                ('dfm', 'openroad', 'openroad'),
                ('export', 'klayout', 'klayout'),
                ('lvs', 'magic', 'klayout'),
                ('drc', 'magic', 'klayout')]

    for i, (step, tool, showtool) in enumerate(flowpipe):
        if i > 0:
            input_step, _, _ = flowpipe[i-1]
            chip.add('flowgraph', step, 'input', input_step)
        chip.set('flowgraph', step, 'tool', tool)
        if showtool:
            chip.set('flowgraph', step, 'showtool', showtool)

    steps = [step for step, _, _ in flowpipe]
    startidx = steps.index(start) if start else 0
    stopidx = steps.index(stop) + 1 if stop else len(steps)
    chip.set('steplist', steps[startidx:stopidx])

def configure_physflow(chip, start=None, stop=None):
    flowpipe = [('import', 'verilator', 'open'),
                ('syn', 'yosys', 'yosys'),
                ('export', 'klayout', 'klayout'),
                ('lvs', 'magic', 'klayout'),
                ('drc', 'magic', 'klayout')]

    for i, (step, tool, showtool) in enumerate(flowpipe):
        if i > 0:
            input_step, _, _ = flowpipe[i-1]
            chip.add('flowgraph', step, 'input', input_step)
        chip.set('flowgraph', step, 'tool', tool)
        if showtool:
            chip.set('flowgraph', step, 'showtool', showtool)

    steps = [step for step, _, _ in flowpipe]
    startidx = steps.index(start) if start else 0
    stopidx = steps.index(stop) + 1 if stop else len(steps)
    chip.set('steplist', steps[startidx:stopidx])

def configure_libs(chip):
    libname = 'io'
    chip.add('asic', 'macrolib', libname)
    chip.set('library', libname, 'type', 'component')
    chip.add('library', libname, 'model', 'typical', 'nldm', 'lib', 'asic/sky130/io/sky130_dummy_io.lib')
    chip.set('library', libname, 'lef', 'asic/sky130/io/sky130_ef_io.lef')
    # Need both GDS files: ef relies on fd one
    chip.add('library', libname, 'gds', 'asic/sky130/io/sky130_ef_io.gds')
    chip.add('library', libname, 'gds', 'asic/sky130/io/sky130_fd_io.gds')
    chip.set('library', libname, 'cells', 'gpio', 'sky130_ef_io__gpiov2_pad')
    chip.set('library', libname, 'cells', 'vdd', 'sky130_ef_io__vccd_hvc_pad')
    chip.set('library', libname, 'cells', 'vddio', 'sky130_ef_io__vddio_hvc_pad')
    chip.set('library', libname, 'cells', 'vss', 'sky130_ef_io__vssd_hvc_pad')
    chip.set('library', libname, 'cells', 'vssio', 'sky130_ef_io__vssio_hvc_pad')
    chip.set('library', libname, 'cells', 'corner', 'sky130_ef_io__corner_pad')
    chip.set('library', libname, 'cells', 'fill1',  'sky130_ef_io__com_bus_slice_1um')
    chip.set('library', libname, 'cells', 'fill5',  'sky130_ef_io__com_bus_slice_5um')
    chip.set('library', libname, 'cells', 'fill10', 'sky130_ef_io__com_bus_slice_10um')
    chip.set('library', libname, 'cells', 'fill20', 'sky130_ef_io__com_bus_slice_20um')

    libname = 'ram'
    chip.add('asic', 'macrolib', libname)
    chip.set('library', libname, 'type', 'component')
    chip.add('library', libname, 'model', 'typical', 'nldm', 'lib', 'asic/sky130/ram/sky130_sram_2kbyte_1rw1r_32x512_8_TT_1p8V_25C.lib')
    chip.add('library', libname, 'lef', 'asic/sky130/ram/sky130_sram_2kbyte_1rw1r_32x512_8.lef')
    chip.add('library', libname, 'gds', 'asic/sky130/ram/sky130_sram_2kbyte_1rw1r_32x512_8.gds')
    chip.set('library', libname, 'cells', 'ram', 'sky130_sram_2kbyte_1rw1r_32x512_8')

def configure_asic_core(chip, start, stop):
    chip.set('design', 'asic_core')
    chip.target('skywater130')
    configure_svflow(chip, start, stop)
    configure_libs(chip)

    # TODO: try using -y flag instead of huge source list in separate file
    add_sources(chip)

    chip.set('constraint', 'asic/asic_core.sdc')

    chip.add('define', 'PRIM_DEFAULT_IMPL="prim_pkg::ImplSky130"')
    chip.add('define', 'RAM_DEPTH=512')

    chip.add('source', 'hw/asic_core.v')
    chip.set('asic', 'def', 'asic_core.def')

    chip.add('source', 'hw/prim/sky130/prim_sky130_ram_1p.v')
    chip.add('source', 'asic/sky130/ram/sky130_sram_2kbyte_1rw1r_32x512_8.bb.v')

def configure_asic_top(chip, start, stop):
    chip.set('design', 'asic_top')
    chip.target('skywater130')
    configure_physflow(chip, start, stop)
    configure_libs(chip)

    # Hack: pass in empty constraint file to get rid of KLayout post-process
    # error (must have same name as design)
    chip.set('constraint', 'asic/asic_top.sdc')

    chip.add('source', 'hw/asic_top.v')
    chip.add('source', 'hw/asic_core.bb.v')
    chip.add('source', 'oh/padring/hdl/oh_padring.v')
    chip.add('source', 'oh/padring/hdl/oh_pads_domain.v')
    chip.add('source', 'oh/padring/hdl/oh_pads_corner.v')

    chip.add('source', 'asic/sky130/io/asic_iobuf.v')
    chip.add('source', 'asic/sky130/io/asic_iovdd.v')
    chip.add('source', 'asic/sky130/io/asic_iovddio.v')
    chip.add('source', 'asic/sky130/io/asic_iovss.v')
    chip.add('source', 'asic/sky130/io/asic_iovssio.v')
    chip.add('source', 'asic/sky130/io/asic_iocorner.v')

    # Dummy blackbox modules just to get synthesis to pass (these aren't
    # acutally instantiated)
    chip.add('source', 'asic/sky130/io/asic_iopoc.v')
    chip.add('source', 'asic/sky130/io/asic_iocut.v')

    chip.add('source', 'asic/sky130/io/sky130_io.blackbox.v')

    chip.set('asic', 'def', 'asic_top.def')

    libname = 'core'
    chip.add('asic', 'macrolib', libname)
    chip.set('library', libname, 'type', 'component')
    chip.set('library', libname, 'lef', 'asic_core.lef')
    chip.set('library', libname, 'gds', 'asic_core.gds')
    chip.set('library', libname, 'cells', 'asic_core', 'asic_core')

def configure_fpga(chip):
    chip.set('design', 'top_icebreaker')
    chip.target('target', 'ice40_fpgaflow')

    add_sources(chip)

    chip.add('source', 'hw/top_icebreaker.v')
    chip.set('constraint', 'fpga/icebreaker.pcf')

def build_fpga(start='import', stop='bitstream'):
    chip = init_chip()
    configure_fpga(chip)
    run_build(chip)

def build_core(start='import', stop='lvs'):
    chip = init_chip()
    configure_asic_core(chip, start, stop)
    core.generate_floorplan(chip)
    run_build(chip)

    # copy out GDS for top-level integration
    if stop in ('export', 'lvs'):
        design = chip.get('design')
        jobdir = (chip.get('build_dir') +
                "/" + design + "/" +
                chip.get('jobname') +
                str(chip.get('jobid')))
        shutil.copy(f'{jobdir}/export0/outputs/{design}.gds', f'{design}.gds')

def build_top(start='import', stop='drc'):
    # check for necessary files generated by previous steps
    if not (os.path.isfile('asic_core.gds') and os.path.isfile('asic_core.lef')):
        raise Exception("Error building asic_top: can't find asic_core outputs. "
                        "Please re-run build.py without --top-only")

    chip = init_chip()
    configure_asic_top(chip, start, stop)
    padring.generate_floorplan(chip)
    run_build(chip)

def build_floorplans():
    chip = init_chip()
    configure_asic_core(chip, 'import', 'export')
    core.generate_floorplan(chip)

    chip = init_chip()
    configure_asic_top(chip, 'import', 'export')
    padring.generate_floorplan(chip)

def run_build(chip):
    chip.run()
    chip.summary()

def main():
    parser = argparse.ArgumentParser(description='Build ZeroSoC')
    parser.add_argument('--fpga', action='store_true', default=False, help='Build for ice40 FPGA (build ASIC by default)')
    parser.add_argument('--core-only', action='store_true', default=False, help='Only build ASIC core GDS.')
    parser.add_argument('--top-only', action='store_true', default=False, help='Only integrate ASIC core into padring. Assumes ASIC core already built.')
    parser.add_argument('--floorplan-only', action='store_true', default=False, help='Generate floorplans only.')
    parser.add_argument('--no-verification', action='store_true', default=False, help="Don't run DRC or LVS.")
    parser.add_argument('-a', '--start', default='import', help='Start step (for single-part builds)')
    parser.add_argument('-z', '--stop', default='drc', help='Stop step (for single-part builds)')
    options = parser.parse_args()

    if options.fpga:
        build_fpga(options.start, options.stop)
    elif options.floorplan_only:
        build_floorplans()
    elif options.core_only:
        build_core(options.start, options.stop)
    elif options.top_only:
        build_top(options.start, options.stop)
    elif options.no_verification:
        build_core(stop='export')
        build_top(stop='export')
    else:
        build_core()
        build_top()

if __name__ == '__main__':
    main()
