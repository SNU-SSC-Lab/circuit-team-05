"""KLayout DRC entry: legacy routing or explicitly expanded geometry profile."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
profile = os.environ.get('SSC_DRC_PROFILE', 'routing')
if profile == 'routing':
    from drc_routing import main
elif profile == 'expanded':
    from drc_geometry import main
else:
    raise ValueError('unknown DRC profile: '+profile)
main()
