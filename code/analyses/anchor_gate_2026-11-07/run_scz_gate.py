import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.chdir(ROOT); sys.path.insert(0, ROOT)
import rebuild_scz_taxonomy_5domain as mod
extra = json.load(open('audit/anchor_gate_2026-11-07/gate_SCZ_extra.json'))
mod.ANCHOR_SET.extend(extra)
print(f'SCZ anchor set: {len(mod.ANCHOR_SET)} terms')
sys.argv = ['rebuild_scz_taxonomy_5domain.py', '--pilot', '--outdir', 'audit/anchor_gate_2026-11-07/run_SCZ',
            '--cache_dir', 'audit/anchor_gate_2026-11-07/run_SCZ/cache'] + sys.argv[1:]
sys.exit(mod.main())
