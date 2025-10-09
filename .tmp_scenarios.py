import asyncio, json, sys, os
print('PYTHONPATH=', os.environ.get('PYTHONPATH'))
from services.semantic_scenario_search import get_semantic_search

async def main():
    ss = await get_semantic_search()
    matches = []
    for k, v in ss._scenario_map.items():
        if 'compliance' in k:
            matches.append((k, len(v.get('queries', [])), v.get('title')))
    print('Compliance-related scenarios:', matches)
    for k, v in ss._scenario_map.items():
        if 'compliance' in k and '10' in k:
            print('\nKey:', k, 'QueryCount:', len(v.get('queries', [])))
            for i,q in enumerate(v.get('queries', []),1):
                print(f'--- Query {i} ---\n{q}\n')

asyncio.run(main())
