cmake_minimum_required(VERSION 3.0.2)
project(benchmark_bluerov2)

## Find catkin macros and libraries
find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  gazebo_ros
  bluerov2_description
)

## Remove this if you're not using a Python setup file
# catkin_python_setup()  # Remove or comment out this line

## Declare catkin package ##
catkin_package(
  CATKIN_DEPENDS rospy std_msgs gazebo_ros bluerov2_description
)

###########
## Build ##
###########

## Specify additional locations of header files
include_directories(
  ${catkin_INCLUDE_DIRS}
)

#############
## Install ##
#############

# If you have Python scripts to install:
catkin_install_python(PROGRAMS
  src/benchmark_subscriber.py
  src/spawn_multiple_rovs.py
  src/run_benchmark_uuv.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

# Mark launch files or other resources for installation
install(DIRECTORY launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

#############
## Testing ##
#############

# Add tests if needed
# catkin_add_gtest(${PROJECT_NAME}-test test/test_benchmark_bluerov2.cpp)
# if(TARGET ${PROJECT_NAME}-test)
#   target_link_libraries(${PROJECT_NAME}-test ${PROJECT_NAME})
# endif()
