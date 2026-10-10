"""Download only the public RockYou password wordlist into project-local .tools."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = 'Passwords/Leaked-Databases/rockyou.txt.tar.gz'


def main():
    folder = ROOT/'.tools/wordlists'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/'rockyou.txt'
    metadata = folder/'rockyou-source.json'
    if target.is_file() and metadata.is_file():
        expected = json.loads(metadata.read_text(encoding='utf-8'))['sha256']
        with target.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise RuntimeError('Local RockYou checksum mismatch')
        print('RockYou verified:', target)
        return 0
    request = Request('https://api.github.com/repos/danielmiessler/SecLists/commits?path='+SOURCE_PATH+'&per_page=1',
                      headers={'User-Agent': 'SDLC-LAB3-wordlist'})
    with urlopen(request, timeout=30) as response:
        commit = json.load(response)[0]['sha']
    url = f'https://raw.githubusercontent.com/danielmiessler/SecLists/{commit}/{SOURCE_PATH}'
    cache = ROOT/'.cache/wordlists'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache/'rockyou.txt.tar.gz'
    with urlopen(url, timeout=90) as response, archive.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    with tarfile.open(archive, 'r:gz') as package:
        members = [member for member in package.getmembers() if member.isfile() and Path(member.name).name == 'rockyou.txt']
        if len(members) != 1 or not 0 < members[0].size <= 256 * 1024 * 1024:
            raise RuntimeError('Unexpected RockYou archive layout or size')
        # Read the one named file; never extract archive paths into the workspace.
        with package.extractfile(members[0]) as stream, target.open('wb') as output:
            shutil.copyfileobj(stream, output)
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata.write_text(json.dumps({'source': url, 'commit': commit, 'sha256': digest,
                                    'bytes': target.stat().st_size}, indent=2)+'\n', encoding='utf-8')
    print('RockYou downloaded:', target, target.stat().st_size, 'bytes; sha256', digest, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
