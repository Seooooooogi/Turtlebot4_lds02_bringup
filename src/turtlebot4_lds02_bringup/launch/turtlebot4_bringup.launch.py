"""TurtleBot4 bringup shim — vendor rplidar.launch.py 자리에 ld08_driver 끼워넣기.

================================================================================
역할 (3-layer hijack pattern Layer 2)
================================================================================
Vendor `turtlebot4_bringup/launch/standard.launch.py` 의 **LiDAR 영역만** 대체하고
그 외 영역은 vendor 자산을 그대로 IncludeLaunchDescription. 즉:

- `rplidar.launch.py`  → 의도적 누락. 자리에 ROBOTIS `ld08_driver` 노드 삽입.
- `robot.launch.py` / `joy_teleop.launch.py` / `description.launch.py` /
  `diagnostics.launch.py`  → vendor 호출 그대로 (vendor 자산 미수정).
- `oakd.launch.py`  → **본 shim 에서 의도적 제외**. 본 repo 의 scope 가
  "LiDAR 영역만 swap" 이며 OAK-D 등 다른 sensor stack 은 vendor `turtlebot4-bringup`
  service 가 별도 경로로 처리하므로 shim 의 미러 대상 아님.

================================================================================
실행 경로
================================================================================
(a) PC standalone 검증 (LDS 미연결 시 ld08_driver 가 enumerate 실패하며 종료):
    ros2 launch turtlebot4_lds02_bringup turtlebot4_bringup.launch.py
(b) TurtleBot4 운영: systemd/override.conf 로 자동 실행
    ExecStart=... ros2 launch turtlebot4_lds02_bringup turtlebot4_bringup.launch.py

================================================================================
namespace 흐름 (토픽 prefix 결정 메커니즘)
================================================================================
$ROBOT_NAMESPACE (env, e.g. "/robot9") → PushRosNamespace → GroupAction 내부의
모든 노드의 effective namespace 가 됨 → ld08_driver 는 토픽 `scan` 을 상대 경로로
발행 → 최종 토픽: "/robot9/scan"

================================================================================
LDS-02 frame_id 정책
================================================================================
ld08_driver 는 `frame_id` 를 launch parameter 로 받음 (default `base_scan`).
TurtleBot4 URDF 의 LiDAR 링크는 `rplidar_link` 이므로, drop-in replacement 를
위해 명시적으로 `rplidar_link` 로 지정 — URDF/Nav2/SLAM stack 변경 0.
"""
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node, PushRosNamespace

from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    lc = LaunchContext()

    # ── Vendor 동작 보존을 위한 환경변수 두 개 ────────────────────────────────
    # TURTLEBOT4_DIAGNOSTICS: vendor standard.launch.py 와 동일하게 '1' 일 때만
    #   diagnostics include. /etc/turtlebot4/setup.bash 에서 export 됨.
    # ROBOT_NAMESPACE: 모든 토픽의 prefix. 예) "/robot9" → 토픽들이 /robot9/...
    diagnostics_enable = EnvironmentVariable('TURTLEBOT4_DIAGNOSTICS', default_value='1')
    namespace = EnvironmentVariable('ROBOT_NAMESPACE', default_value='')

    # ── 패키지 share 디렉터리 해소 ────────────────────────────────────────────
    # vendor 패키지 3 종은 IncludeLaunchDescription 으로 호출 — 직접 수정 없음.
    pkg_turtlebot4_bringup = get_package_share_directory('turtlebot4_bringup')
    pkg_turtlebot4_diagnostics = get_package_share_directory('turtlebot4_diagnostics')
    pkg_turtlebot4_description = get_package_share_directory('turtlebot4_description')

    # ── Launch arguments ──────────────────────────────────────────────────────
    # param_file: vendor turtlebot4.yaml — robot.launch.py 가 사용 (create3 등).
    param_file_cmd = DeclareLaunchArgument(
        'param_file',
        default_value=PathJoinSubstitution(
            [pkg_turtlebot4_bringup, 'config', 'turtlebot4.yaml']),
        description='TurtleBot4 robot param file (vendor)'
    )

    param_file = LaunchConfiguration('param_file')

    # ── vendor turtlebot4.yaml 의 namespace rewrite ──────────────────────────
    # vendor robot.launch.py 가 받는 turtlebot4.yaml 은 root key 가 고정 namespace.
    # ROBOT_NAMESPACE 가 변경되어도 YAML 의 root key 는 그대로이므로 nav2_common 의
    # RewrittenYaml 로 root_key 만 동적 치환.
    namespaced_param_file = RewrittenYaml(
        source_file=param_file,
        root_key=namespace,
        param_rewrites={},
        convert_types=True)

    turtlebot4_robot_launch_file = PathJoinSubstitution(
        [pkg_turtlebot4_bringup, 'launch', 'robot.launch.py'])
    joy_teleop_launch_file = PathJoinSubstitution(
        [pkg_turtlebot4_bringup, 'launch', 'joy_teleop.launch.py'])
    diagnostics_launch_file = PathJoinSubstitution(
        [pkg_turtlebot4_diagnostics, 'launch', 'diagnostics.launch.py'])
    description_launch_file = PathJoinSubstitution(
        [pkg_turtlebot4_description, 'launch', 'robot_description.launch.py'])

    # ── LDS-02 (LD08) LiDAR 노드 ──────────────────────────────────────────────
    # executable 이름은 'ld08_driver' (NOT 'ld08_driver_node') — vendor 1.1.4 검증.
    # frame_id 를 'rplidar_link' 로 지정해 vendor URDF 와 일치 → drop-in replacement.
    # 노출 파라미터: frame_id, namespace 두 개뿐. port/device 같은 파라미터는 미존재
    # (드라이버 내부에서 libudev 로 USB descriptor 자동 탐지).
    ld08_node = Node(
        package='ld08_driver',
        executable='ld08_driver',
        name='ld08_driver',
        output='screen',
        parameters=[
            {'frame_id': 'rplidar_link'},
        ],
    )

    # ── actions 묶음 ─────────────────────────────────────────────────────────
    # vendor standard.launch.py 와 동일 순서로 robot/joy/lidar/description/
    # diagnostics 를 호출. 단, vendor rplidar.launch.py 자리에 ld08_node 삽입.
    # PushRosNamespace 가 GroupAction 의 첫 action 이라야 후속 모든 노드에 적용됨.
    actions = [
        # PushRosNamespace: GroupAction 내부 모든 노드의 effective namespace 설정.
        PushRosNamespace(namespace),

        # robot.launch.py: create3 driver + topic bridge.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([turtlebot4_robot_launch_file]),
            launch_arguments=[('model', 'standard'),
                              ('param_file', namespaced_param_file)]),

        # joy_teleop.launch.py: 조이스틱 teleop.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([joy_teleop_launch_file]),
            launch_arguments=[('namespace', namespace)]),

        # vendor rplidar.launch.py 자리 — 의도적 누락. LDS-02 노드로 대체.
        # 발행 토픽: /<ns>/scan (sensor_msgs/LaserScan, frame_id=rplidar_link)
        ld08_node,

        # robot_description.launch.py: URDF + robot_state_publisher.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([description_launch_file]),
            launch_arguments=[('model', 'standard')]),
    ]

    # ── diagnostics 조건부 추가 ───────────────────────────────────────────────
    # vendor standard.launch.py 와 동일하게 TURTLEBOT4_DIAGNOSTICS=1 일 때만 include.
    if diagnostics_enable.perform(lc) == '1':
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource([diagnostics_launch_file]),
            launch_arguments=[('namespace', namespace)]))

    ld = LaunchDescription()
    ld.add_action(param_file_cmd)
    ld.add_action(GroupAction(actions))
    return ld
