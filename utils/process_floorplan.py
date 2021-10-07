#!/usr/bin/env python3

import siliconcompiler
import siliconcompiler.floorplan

import os
import shutil
import subprocess

if 'SC_HOME' in os.environ:
    SC_HOME = os.environ['SC_HOME']
else:
    SC_HOME = None

SCREENSHOTS = False
GENERATE_DEFS = False
GENERATE_SPHINX = False

def dump_def(fp_code, filename, design):
    scope = {}

    exec(fp_code, scope)
    chip = scope['configure_chip'](design)
    fp = siliconcompiler.floorplan.Floorplan(chip)
    if design == 'asic_core':
        scope['core_floorplan'](fp)
    elif design == 'asic_top':
        scope['top_floorplan'](fp)

    basename = os.path.splitext(filename)[0]

    os.makedirs('tmp', exist_ok=True)
    fp.write_def(f'tmp/{basename}.def')

    return def_file

def screenshot(fp_code, filename, design):
    def_file = dump_def(fp_code, filename, design)

    if SCREENSHOTS:
        cmd = f'klayout -z -rd input_layout={def_file} -rm scrotLayout.py'
        subprocess.run(cmd, shell=True)

        shutil.copy(f'tmp/{filename}', f'{SC_HOME}/docs/tutorials/_images')

def main():
    full_floorplan = ''
    snippets = {}
    full_snippets = {}

    with open('floorplan_template.py', 'r') as infile:
        for line in infile.read().split('\n'):
            stripped_line = line.lstrip()
            if stripped_line.startswith('#@'):
                _, command, name = stripped_line.split()
                if command == 'begin':
                    snippets[name] = ''
                elif command == 'end':
                    full_snippets[name] = ''
                    snippet_text = snippets[name]
                    leading_spaces = len(snippet_text) - len(snippet_text.lstrip(' '))
                    full_snippets[name] = '\n'.join([snipline[leading_spaces:] for snipline in snippet_text.split('\n')])
                    del snippets[name]
                elif command == 'screenshot':
                    if SCREENSHOTS:
                        screenshot(full_floorplan, name, 'asic_core')
                elif command == 'screenshottop':
                    if SCREENSHOTS:
                        screenshot(full_floorplan, name, 'asic_top')
                elif command == 'def':
                    if GENERATE_DEFS:
                        dump_def(full_floorplan, name, 'asic_core')
                elif command == 'deftop':
                    if GENERATE_DEFS:
                        dump_def(full_floorplan, name, 'asic_top')
                continue

            for key in snippets.keys():
                snippets[key] += line + '\n'
            full_floorplan += line + '\n'

    with open(f'floorplan.py', 'w') as outfile:
        outfile.write(full_floorplan)

    full_tutorial = ''
    with open('zerosoc_template.rst') as infile:
        for line in infile.read().split('\n'):
            if line.startswith('..@include'):
                _, snippet = line.split()
                full_tutorial += '\n'.join([(' ' * 2 + snipline).rstrip() for snipline in full_snippets[snippet].split('\n')])
            else:
                full_tutorial += line + '\n'

    if SC_HOME is not None:
        path = f'{SC_HOME}/docs/tutorials/zerosoc.rst'
    else:
        path = 'zerosoc.rst'

    with open(path, 'w') as outfile:
        outfile.write(full_tutorial)

    if GENERATE_SPHINX and SC_HOME is not None:
        os.chdir(f'{SC_HOME}/docs')
        subprocess.run('make html', shell=True)

if __name__ == '__main__':
    main()
