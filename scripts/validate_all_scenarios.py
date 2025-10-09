import asyncio, json, sys
from pathlib import Path
root = Path(__file__).parent.parent
backend = root / 'backend'
for p in (root, backend):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from services.instructions_parser import parse_instructions  # noqa: E402
from services.semantic_scenario_search import get_semantic_search  # noqa: E402

async def main():
    text = Path('instructions.md').read_text(encoding='utf-8')
    parsed = parse_instructions(text)
    parsed_map = {p['title']: p for p in parsed}
    ss = await get_semantic_search()

    # Build list of semantic scenario titles (from scenario_map)
    sem_titles = [v.get('title') for v in ss._scenario_map.values() if v.get('title')]

    combined_titles = sorted(set(list(parsed_map.keys()) + sem_titles))

    rows = []
    missing_queries = []
    for title in combined_titles:
        p_entry = parsed_map.get(title)
        q_count = len(p_entry['queries']) if p_entry else 0
        sem_norm = None
        sem_q_count = None
        # Build normalized key and attempt semantic lookup
        # We lean on internal normalization via access pattern
        from services.semantic_scenario_search import _normalize_title_key  # type: ignore
        norm = _normalize_title_key(title)
        scen = ss.get_scenario_by_normalized(norm)
        if scen:
            sem_norm = norm
            sem_q_count = len(scen.get('queries', []))
        rows.append({
            'title': title,
            'parsed_queries': q_count,
            'semantic_queries': sem_q_count,
            'normalized_key': sem_norm
        })
        if q_count == 0:
            missing_queries.append(title)

    print("SCENARIO COVERAGE SUMMARY")
    for r in rows:
        print(f"- {r['title']} | parsed={r['parsed_queries']} semantic={r['semantic_queries']}")
    print("\nTOTAL scenarios discovered:", len(rows))
    print("Scenarios with 0 parsed queries:", len(missing_queries))
    if missing_queries:
        print("List of missing query scenarios:")
        for t in missing_queries:
            print("  *", t)

    # Emit JSON for potential programmatic use
    Path('.scenario_validation.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')

if __name__ == '__main__':
    asyncio.run(main())
