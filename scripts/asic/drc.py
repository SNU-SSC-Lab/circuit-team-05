"""KLayout DRC entry: legacy routing, explicitly expanded geometry profile, or the kit ANT deck (antenna)."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
profile = os.environ.get('SSC_DRC_PROFILE', 'routing')
if profile == 'routing':
    from drc_routing import main
elif profile == 'expanded':
    from drc_geometry import main
elif profile == 'antenna':
    from drc_antenna import main
else:
    raise ValueError('unknown DRC profile: '+profile)
main()
