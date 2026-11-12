"""Install this repository's Git hook without overwriting another hook setup."""
import subprocess
import sys
from pathlib import Path

from policy import PolicyError, git, root_at


def install(root: Path) -> None:
    result = subprocess.run(['git', '-C', str(root), 'config', '--get', 'core.hooksPath'],
                            capture_output=True, text=True)
    existing = result.stdout.strip()
    if existing and existing != '.githooks':
        raise PolicyError(f'기존 hooksPath={existing}를 덮어쓰지 않습니다. 수동으로 함께 구성하세요.')
    if not (root / '.githooks/pre-push').is_file():
        raise PolicyError('저장소의 pre-push 파일이 없습니다.')
    git(root, 'config', '--local', 'core.hooksPath', '.githooks')
    (root / '.githooks/pre-push').chmod(0o755)
    print('이 저장소의 Git pre-push 설치 완료. 에이전트 훅의 신뢰·활성화는 별도 확인하세요.')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        install(root_at('.'))
    except PolicyError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
