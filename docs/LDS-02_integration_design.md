# LDS-02 Integration Design & Verification Guide

> 검증 기준: `ros-humble-ld08-driver` 1.1.4, `ros-humble-turtlebot4-bringup` 1.0.3, `ros-humble-turtlebot4-description` 1.0.5
> Last verified: 2026-04-28

본 문서는 이 프로젝트의 **설계 근거**와 **현장 검증 절차**를 정리한 reference 다. 구현 자체는 `src/turtlebot4_lds02_bringup/` 의 launch / systemd / udev 파일에 이미 반영돼 있다.

## 통합 구조

TurtleBot4 vendor 브링업을 **3-레이어 hijack 패턴**으로 우회한다:

- **Layer 3 (systemd drop-in)**: `src/turtlebot4_lds02_bringup/systemd/override.conf` → 설치 위치 `/etc/systemd/system/turtlebot4.service.d/override.conf`. vendor `ExecStart` 를 새 값으로 override — 우리 launch shim 이 진입점이 됨.
- **Layer 2 (launch shim)**: `src/turtlebot4_lds02_bringup/launch/turtlebot4_bringup.launch.py` — vendor `standard.launch.py` 흐름을 그대로 재현하되 `rplidar.launch.py` 만 빼고 `ld08_driver` 노드를 끼워넣음. `IncludeLaunchDescription` 으로 vendor robot/joy/description 호출 — vendor 자산 미수정.
- **Layer 1 (node)**: vendor `ld08_driver` 1.1.4 (apt 정식 배포) 를 **그대로** 사용 — 자체 노드 작성 없음.

핵심 원칙: **vendor 패키지 코드 미수정**. systemd drop-in + launch shim + udev 룰 만으로 LDS-02 통합.

## 사전 검증된 사실

vendor 1.1.4 배포 검증 결과:

1. **executable 이름은 `ld08_driver`** (`_node` 접미사 없음). vendor `ld08.launch.py` 와 binary `lib/ld08_driver/ld08_driver` 일치.
2. **노출 파라미터는 `frame_id`, `namespace` 두 개뿐**. `product_name`, `port`, `device` 같은 파라미터는 **존재하지 않음** (binary strings 분석).
3. **장치 자동 탐지**: 드라이버는 `libudev` 로 USB 디바이스를 직접 enumerate — `/dev/ttyUSB*` 경로를 launch 파라미터로 받지 않음. udev 룰의 `SYMLINK+=` 는 드라이버 동작에 영향 없음 (사람용 별칭일 뿐).
4. **TurtleBot4 URDF 의 LiDAR 프레임 = `rplidar_link`** — `turtlebot4_description/urdf/standard/turtlebot4.urdf.xacro:114` 에서 `<xacro:rplidar name="rplidar" parent_link="shell_link">` 로 인스턴스화 → 링크 이름 `rplidar_link`.
5. **vendor `rplidar.launch.py`** 는 `frame_id: 'rplidar_link'`, `serial_port: '/dev/RPLIDAR'`, baudrate 115200 으로 publish — RPLIDAR-A1 교체 시 동일 frame_id 를 LDS-02 에서 그대로 publish 하면 URDF/Nav2/SLAM stack 변경 0.

## 설계 결정 사항

### frame_id = `rplidar_link`

`ld08_driver` 의 default `frame_id` 는 `base_scan` 이지만, drop-in replacement 를 위해 **`rplidar_link`** 으로 override (URDF 의 링크 이름과 일치). → URDF/Nav2/SLAM stack 변경 0. 구현: `launch/turtlebot4_bringup.launch.py` 의 `parameters=[{'frame_id': 'rplidar_link'}]`.

대안인 `static_transform_publisher` 로 `rplidar_link → base_scan` aliasing 은 **사용하지 않음** — 드라이버가 직접 frame_id 를 받으므로 추가 노드/extra TF/timestamp 지연만 유발.

### inline `Node` action vs `IncludeLaunchDescription`

vendor `ld08.launch.py` 는 `Node` 한 개만 감싸므로 inline `Node` 와 등가. 본 프로젝트는 inline Node 선택 — 의존성 그래프가 명시적이고 실패 진단이 단순함. vendor launch 가 향후 추가 Node 를 도입한다면 `IncludeLaunchDescription` 으로 전환 검토.

### USB descriptor 검증 (CP2102)

PC 에 직접 연결하여 2026-04-28 측정한 LDS-02 보드 1 대 기준:

| 속성 | 값 |
|------|-----|
| idVendor | `10c4` (Silicon Labs) |
| idProduct | `ea60` (CP2102 USB to UART Bridge) |
| serial | `0001` (제조사가 unique serial 미주입) |

→ udev 룰 `SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666"` 로 매칭. 보드 리비전이 다른 칩을 사용한다면 `lsusb` / `udevadm info -a -n /dev/ttyUSB0` 로 재확인 후 룰 갱신.

### CP2102 동종 디바이스 충돌 (단일 LiDAR 운용 가정)

RPLIDAR-A1 도 보통 CP2102 (`10c4:ea60`) 를 쓰며, 위 LDS-02 의 serial 이 generic `0001` 이라 vendor/product/serial 조합으로 disambiguate 불가. 본 프로젝트는 **LDS-02 단독 운용** 가정 → RPLIDAR 물리 제거 시 충돌 없음. 듀얼 LiDAR 시나리오가 발생하면 udev 룰을 USB 포트 경로 (`KERNELS=="1-1.2"` 등) 로 disambiguate 필요 (`udevadm info -a -n /dev/ttyUSB0 | grep KERNELS` 로 확인).

## 설치 / 배포

TurtleBot4 RPi4 에서 다음 순서:

```bash
# 1. ld08_driver 설치
sudo apt install ros-humble-ld08-driver
ros2 pkg executables ld08_driver        # 'ld08_driver ld08_driver' 출력 확인

# 2. 워크스페이스 clone & build
cd ~ && git clone <REPO_URL> Turtlebot4_lds02_bringup_ws
cd ~/Turtlebot4_lds02_bringup_ws
# (이 레포 자체가 워크스페이스 — src/ 내부에 패키지 1개)
# 또는 src/ 만 분리해 별도 워크스페이스에 둘 수도 있음
colcon build --symlink-install

# 3. udev 룰 설치
sudo install -m 0644 \
  ~/Turtlebot4_lds02_bringup_ws/src/turtlebot4_lds02_bringup/udev/99-lds02.rules \
  /etc/udev/rules.d/99-lds02.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/ttyUSB0   # crw-rw-rw- 확인

# 4. systemd drop-in 설치
sudo install -d /etc/systemd/system/turtlebot4.service.d
sudo install -m 0644 \
  ~/Turtlebot4_lds02_bringup_ws/src/turtlebot4_lds02_bringup/systemd/override.conf \
  /etc/systemd/system/turtlebot4.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart turtlebot4.service

# 5. 모니터링
sudo journalctl -u turtlebot4.service -f
```

> 워크스페이스 경로가 `~/Turtlebot4_lds02_bringup_ws` 가 아니면 `systemd/override.conf` 의 `source ...install/setup.bash` 라인 수정 필요.

## 검증 체크리스트

### PC dry-run (LDS 미연결 환경)

- [ ] `colcon build --symlink-install` 에러 없음
- [ ] `ros2 pkg executables ld08_driver` 출력에 `ld08_driver` 포함
- [ ] `ros2 launch turtlebot4_lds02_bringup turtlebot4_bringup.launch.py` — vendor 패키지 미설치 시 import 에러는 정상 (PC 에 turtlebot4_bringup 미설치). LDS 미연결로 ld08_driver enumerate 실패하며 종료되는 것도 정상.

### TurtleBot4 실기

- [ ] `ros2 topic list` 에 `/<ROBOT_NAMESPACE>/scan` 노출
- [ ] `ros2 topic hz /<ROBOT_NAMESPACE>/scan` → ~5–10 Hz (LDS-02 사양)
- [ ] `ros2 topic echo /<ROBOT_NAMESPACE>/scan --once` 의 `header.frame_id == "rplidar_link"`
- [ ] `ros2 run tf2_ros tf2_echo base_link rplidar_link` 정상 (URDF 변경 0 이므로 자동 통과 예상)
- [ ] RViz: Fixed Frame `base_link` 에서 `/scan` 시각화 — 360° 포인트 정상
- [ ] 시스템 재부팅 후 systemd 자동기동에서 위 항목 모두 동일

### QoS 호환성

```bash
ros2 topic info /<ns>/scan --verbose
```
`Reliability`, `Durability`, `History` 가 SLAM/Nav2 subscriber 와 일치하는지 확인. 충돌 시 subscriber 측 QoS override.

## 절대 하지 말 것

- vendor `turtlebot4_bringup` / `turtlebot4_description` 패키지 소스 수정
- `ld08_driver` 패키지 소스 수정 / fork — 현재 노출된 `frame_id`, `namespace` 파라미터로 모든 통합 요건 충족
- systemd `turtlebot4.service` 본체 수정 (drop-in override.conf 만 사용)
- `static_transform_publisher` 로 frame aliasing 우회 — 드라이버가 frame_id 를 받으므로 불필요
- `frame_id` 를 `rplidar_link` 가 아닌 다른 값으로 변경 — URDF/Nav2/SLAM stack 영향 광범위

## 롤백 절차

문제 발생 시 RPLIDAR-A1 으로 복구:

1. systemd override 비활성: `sudo rm /etc/systemd/system/turtlebot4.service.d/override.conf && sudo systemctl daemon-reload && sudo systemctl restart turtlebot4.service` → vendor 기본 흐름 복구
2. (선택) udev 룰 제거: `sudo rm /etc/udev/rules.d/99-lds02.rules && sudo udevadm control --reload-rules`
3. 물리 LiDAR 교체 (LDS-02 → RPLIDAR-A1)

## 스펙 비교 (RPLIDAR-A1 ↔ LDS-02)

| 항목 | RPLIDAR-A1 (A1M8) | LDS-02 (LD08) |
|------|-------------------|----------------|
| 측정 거리 | 0.15 – 6 m | 0.16 – 8 m |
| 거리 정확도 | < 1% of distance | ±10 mm @ 0.16–0.3 m / ±3% @ 0.3–6 m / ±5% @ 6–8 m |
| 각 분해능 | ≤ 1° (@ 5.5 Hz) | 1° |
| FOV | 360° | 360° |
| Scan rate | 1 – 10 Hz (typ 5.5) | ≥ 5 Hz (unit 별 변동) |
| Sample rate | ≥ 2 kHz typ | 2.3 kHz fixed |
| 광원 | 785 nm IR / 3 mW typ / Class I | 793 nm IR / Class I |
| 환경광 내성 | "outdoor without sunlight" 권장 | 25,000 lux |
| 전원 | 5 V scanner + 5–10 V motor | 5 V ±10% (240 mA, startup 400 mA) |
| ROS 출력 | `sensor_msgs/LaserScan`, `/scan` | `sensor_msgs/LaserScan`, `/scan` |

drop-in 가능. 장점: 측정 거리 +2 m, 환경광 내성 강함, 단일 5 V 전원. 약점: 6–8 m 구간 ±5% noise, unit 별 scan rate 변동.

### Nav2 / SLAM toolbox 권장 파라미터 재검토

| 파라미터 | 권장 | 이유 |
|----------|------|------|
| Nav2 `obstacle_max_range` | 4–5 m | LDS-02 신뢰 영역 (±3% 까지) 활용 |
| Nav2 `raytrace_max_range` | 5 m | obstacle_max_range 보다 약간 크게 |
| SLAM toolbox `max_laser_range` | 6 m (기본), 8 m (감수) | 6 m 초과는 noise 큼 |
| `min_laser_range` | 0.20 m | 0.16–0.3 m 구간 ±10 mm 절대오차 보수적 컷 |
