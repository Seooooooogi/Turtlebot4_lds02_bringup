cmake_minimum_required(VERSION 3.10)
project(turtlebot4_lds02_bringup)

find_package(ament_cmake REQUIRED)

# Pure launch / config / systemd / udev install — no C++ targets.
install(DIRECTORY launch rviz systemd udev
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
