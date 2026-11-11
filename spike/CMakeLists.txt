# Standalone project for the signal-blocks spike. It builds the library from
# the parent directory, unchanged, and is not reached from the root
# CMakeLists.txt or from any preset.
#
#   cmake -S spike -B build/spike -G Ninja -DCMAKE_BUILD_TYPE=Release
#   cmake --build build/spike
#   build/spike/spike_runner spike/vectors

cmake_minimum_required(VERSION 3.20)
project(fluxgraph_spike LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(FLUXGRAPH_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(FLUXGRAPH_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/.. ${CMAKE_CURRENT_BINARY_DIR}/fluxgraph)

add_executable(spike_runner runner.cpp blocks.cpp)
target_link_libraries(spike_runner PRIVATE fluxgraph)
target_compile_options(spike_runner PRIVATE -Wall -Wextra -Wpedantic)
