# Turtlebot4_lds02_bringup

TurtleBot4 (Humble) 의 vendor RPLIDAR-A1 를 ROBOTIS **LDS-02 (LD08)** 로 교체하기 위한 bringup shim. **vendor 패키지를 수정하지 않고** systemd drop-in / launch shim / udev 룰 세 레이어로 LiDAR 노드만 swap-in 한다.

## 구성

```
src/turtlebot4_lds02_bringup/
├── launch/
│   └── turtlebot4_bringup.launch.py   # vendor standard.launch.py 미러 + ld08_driver 삽입
├── systemd/
│   └── override.conf                   # turtlebot4.service drop-in
└── udev/
    └── 99-lds02.rules                  # CP2102 USB-serial 권한 룰
```

자체 ROS 노드 없음 — vendor `ld08_driver` (apt: `ros-humble-ld08-driver`) 를 그대로 사용.

## 빠른 설치 (TurtleBot4 RPi4)

```bash
sudo apt install ros-humble-ld08-driver

git clone https://github.com/Seooooooogi/Turtlebot4_lds02_bringup.git ~/Turtlebot4_lds02_bringup_ws
cd ~/Turtlebot4_lds02_bringup_ws
colcon build --symlink-install
source install/setup.bash

# udev 룰
sudo install -m 0644 src/turtlebot4_lds02_bringup/udev/99-lds02.rules /etc/udev/rules.d/99-lds02.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# systemd drop-in
sudo install -d /etc/systemd/system/turtlebot4.service.d
sudo install -m 0644 src/turtlebot4_lds02_bringup/systemd/override.conf /etc/systemd/system/turtlebot4.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart turtlebot4.service
```

상세한 설계 근거 / 검증 절차 / 롤백은 [`docs/LDS-02_integration_design.md`](docs/LDS-02_integration_design.md) 참조.

## 검증

```bash
ros2 topic hz /<ROBOT_NAMESPACE>/scan        # ~5–10 Hz
ros2 topic echo /<ROBOT_NAMESPACE>/scan --once    # frame_id == "rplidar_link"
ros2 run tf2_ros tf2_echo base_link rplidar_link  # URDF TF 정상
```

## 의존성

- ROS 2 Humble
- `ros-humble-ld08-driver` 1.1.4+
- `ros-humble-turtlebot4-bringup` 1.0.3+
- `ros-humble-turtlebot4-description` 1.0.5+
- `ros-humble-turtlebot4-diagnostics` (선택, `TURTLEBOT4_DIAGNOSTICS=1` 시)
- `ros-humble-nav2-common` (RewrittenYaml 용)

## 라이선스

Apache 2.0
