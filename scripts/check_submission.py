"""Check staged files without printing secrets; run after git add."""
import re
import subprocess
from pathlib import Path


def main():
    files=subprocess.check_output(['git','diff','--cached','--name-only','-z']).decode('utf-8').split('\0')
    failures=[]
    for name in filter(None,files):
        parts=Path(name).parts
        if '.env' in parts or any(p in parts for p in ['node_modules','.venv','runtime']):
            failures.append(name+': forbidden local artifact')
            continue
        if name.endswith('.png'): continue
        data=subprocess.check_output(['git','show',':'+name])
        if re.search(rb'sk-[A-Za-z0-9]{20,}',data):
            failures.append(name+': possible credential (value not displayed)')
    required=['README.md','.env.example','requirements.lock.txt','frontend/package-lock.json',
        'docs/01-requirements.md','docs/02-solution.md','docs/03-evaluation.md',
        'docs/04-ai-usage.md','docs/05-retrospective.md','examples/live/report.json','examples/mock/report.json']
    failures += [name+': missing' for name in required if not Path(name).is_file()]
    if failures:
        print('\n'.join(failures))
        raise SystemExit(1)
    print(f'PASS: {len(list(filter(None,files)))} staged files checked; no credential patterns or local artifacts found.')


if __name__=='__main__':
    main()
