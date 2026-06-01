# Video Frames

<p align="center">
  <img src="assets/AppIcon_1024.png" width="160" alt="Video Frames app icon">
</p>

비디오 파일을 드래그 앤 드롭하면 모든 프레임을 JPG로 추출해주는 가장 단순한 macOS 앱.

- FFmpeg CLI를 외울 필요 없이 끌어놓기만 하면 됩니다
- 비디오와 같은 폴더에 `{이름}/` 폴더를 만들어 `{이름}_000001.jpg` 형태로 정리해줍니다
- ffmpeg가 `.app` 안에 내장되어 있어 Homebrew 등 사전 설치가 필요 없습니다

## 주요 기능

- 드래그 앤 드롭 / 파일 선택 버튼
- 비디오 메타데이터 미리보기 (해상도 · 길이 · fps · 총 프레임 수 · 코덱)
- JPG 품질 슬라이더 (1–100, 기본 90) · 마지막 값 기억
- 예상 출력 용량 표시
- 실시간 진행률 + 취소
- 동일 이름 폴더 충돌시 덮어쓰기 / 새 이름 / 취소 선택
- 완료 후 결과 폴더 바로 열기

지원 입력: `.mp4`, `.mov`, `.m4v`, `.avi`, `.mkv`, `.webm`, `.flv`, `.wmv`, `.mpg`, `.mpeg`, `.ts`

## 시스템 요구사항

- macOS 11 (Big Sur) 이상
- Apple Silicon (M1/M2/M3/M4 …)
- 약 200MB 디스크 공간

> Intel Mac에서 사용하려면 Intel Mac에서 직접 빌드해야 합니다 (PyQt6 휠이 아키텍처별).

## 설치

### 미리 빌드된 `.app` 사용

[Releases](https://github.com/viscozegit/VideoFrames/releases)에서 `VideoFrames.zip`을 받아 압축을 풀고 `Video Frames.app`을 `/Applications`로 옮기세요.

첫 실행시 Gatekeeper 경고가 뜨면 **앱을 우클릭 → 열기**로 한 번만 허용해주면 됩니다 (ad-hoc 서명만 되어 있어서).

### 소스에서 빌드

```bash
git clone https://github.com/viscozegit/VideoFrames.git
cd VideoFrames

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller Pillow

bash scripts/build.sh
open dist/Video\ Frames.app
```

빌드 스크립트가 자동으로:
1. `imageio-ffmpeg`에서 정적 ffmpeg 바이너리를 가져와 `vendor/bin/ffmpeg`에 스테이징
2. PyInstaller로 `.app` 번들 생성 (ffmpeg는 `Contents/Frameworks/bin/ffmpeg`에 동봉됨)
3. 다운로드 quarantine 속성 제거 + ad-hoc codesign

최종 `.app` 크기는 약 160MB입니다.

## 개발 (소스로 직접 실행)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

`imageio-ffmpeg`가 ffmpeg를 자동으로 제공하므로 별도 설치 없이 바로 동작합니다.

## 프로젝트 구조

```
.
├── main.py              # 엔트리포인트
├── gui.py               # PyQt6 메인 윈도우 · 다이얼로그
├── extractor.py         # ffmpeg 호출 · 메타데이터 probe · 진행률
├── config.py            # 마지막 품질 값 영속화
├── VideoFrames.spec     # PyInstaller 번들 정의
├── scripts/
│   ├── build.sh         # 엔드 투 엔드 빌드
│   └── make_icon.py     # .icns 아이콘 생성
└── assets/
    ├── AppIcon.icns
    └── AppIcon_1024.png
```

## 기술 스택

- Python 3.9+
- [PyQt6](https://pypi.org/project/PyQt6/) — GUI
- [imageio-ffmpeg](https://pypi.org/project/imageio-ffmpeg/) — 정적 ffmpeg 바이너리 공급
- [PyInstaller](https://pyinstaller.org) — `.app` 번들 패키징

자세한 제품 사양은 [PRD.md](PRD.md) 참조.
