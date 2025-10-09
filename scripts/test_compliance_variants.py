import asyncio, sys
from pathlib import Path
root = Path(__file__).parent.parent
backend = root / 'backend'
for p in (root, backend):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from services.semantic_scenario_search import get_semantic_search
from services.instructions_parser import parse_instructions
import hashlib

# Reuse normalization from agent_framework_service
from services.agent_framework_service import _normalize_query_for_hash  # type: ignore

async def main():
    text = Path('instructions.md').read_text(encoding='utf-8')
    parsed = parse_instructions(text)
    target = next(p for p in parsed if 'Device Compliance' in p['title'])
    original = target['queries'][0]
    function_only = original
    # remove cluster().database() prefix to simulate truncated agent variant
    import re
    m = re.search(r"cluster\(.*?\)\.database\(.*?\)\.(.+)$", original, re.DOTALL)
    if m:
        function_only = m.group(1).strip()
    print('Original Query:', original)
    print('Function-only Variant:', function_only)
    orig_hash = hashlib.sha256(_normalize_query_for_hash(original).encode()).hexdigest()
    func_hash = hashlib.sha256(_normalize_query_for_hash(function_only).encode()).hexdigest()
    print('Original Hash:', orig_hash)
    print('Function-only Hash:', func_hash)
    ss = await get_semantic_search()
    scen = ss.get_scenario_by_normalized('device_compliance_last_10_days')
    print('Scenario queries (post-lock build may differ) length:', len(scen.get('queries', []) if scen else []))
    # We can't directly access SCENARIO_LOCK here without initiating lookup_scenarios path, but we at least show hashes.

if __name__ == '__main__':
    asyncio.run(main())
