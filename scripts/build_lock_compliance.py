import asyncio, sys
from pathlib import Path
root = Path(__file__).parent.parent
backend = root / 'backend'
for p in (root, backend):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from services.agent_framework_service import create_scenario_lookup_function, SCENARIO_LOCK  # type: ignore
from services.semantic_scenario_search import get_semantic_search

async def main():
    ss = await get_semantic_search()
    await ss.initialize()
    lookup = create_scenario_lookup_function()
    # Use a compliance-only prompt (no policy words)
    res = await lookup('compliance status for device 12345678-1234-1234-1234-123456789abc')
    print('Lookup response first line:', res.splitlines()[0])
    global SCENARIO_LOCK
    print('LOCK:', SCENARIO_LOCK)

if __name__ == '__main__':
    asyncio.run(main())
