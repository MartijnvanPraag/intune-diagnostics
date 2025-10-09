from services.instructions_parser import parse_instructions
import pathlib
text=pathlib.Path('instructions.md').read_text(encoding='utf-8')
scs=parse_instructions(text)
print([(s['title'], len(s['queries'])) for s in scs if 'Compliance' in s['title']])
for s in scs:
    if 'Device Compliance (Last 10 Days)'==s['title']:
        print('Queries:')
        for q in s['queries']:
            print('---\n'+q+'\n---')
