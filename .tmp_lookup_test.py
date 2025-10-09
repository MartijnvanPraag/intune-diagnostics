import asyncio, json
from services.agent_framework_service import create_scenario_lookup_function
from services.semantic_scenario_search import get_semantic_search

async def main():
    ss = await get_semantic_search()
    await ss.initialize()
    fn = create_scenario_lookup_function()
    result = await fn('device details for X')
    first_line = result.splitlines()[0]
    print(first_line)
    json.loads(first_line)
    print('FIRST LINE JSON OK')
    print('Lines:', len(result.splitlines()))

asyncio.run(main())
