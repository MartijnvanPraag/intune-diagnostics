import asyncio
import sys, os
from pathlib import Path

# Ensure backend package is importable when running under `uv run` without env var
root = Path(__file__).parent.parent
backend = root / 'backend'
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from services.semantic_scenario_search import get_semantic_search  # noqa: E402
from services.instructions_parser import parse_instructions  # noqa: E402

async def main():
    ss = await get_semantic_search()
    # Force re-init parse directly
    text = Path('instructions.md').read_text(encoding='utf-8')
    parsed = parse_instructions(text)
    target = [p for p in parsed if 'Device Compliance (Last 10 Days)' == p['title']]
    print('Parsed compliance scenario (direct):', [(p['title'], len(p['queries'])) for p in target])
    if target and target[0]['queries']:
        print('First query direct:\n', target[0]['queries'][0])
    scen = ss.get_scenario_by_normalized('device_compliance_last_10_days')
    if scen:
        print('Semantic map compliance scenario queries:', len(scen.get('queries', [])))
        if scen.get('queries'):
            print('First query semantic:\n', scen['queries'][0])
    else:
        print('Semantic map: compliance scenario not found')

if __name__ == '__main__':
    asyncio.run(main())
