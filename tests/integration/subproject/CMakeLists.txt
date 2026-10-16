cmake_minimum_required(VERSION 3.20)

# A consumer that embeds fluxgraph with add_subdirectory and sets no
# fluxgraph options. Configured by subproject_defaults.cmake.
project(fluxgraph_subproject_consumer LANGUAGES CXX)

add_subdirectory("${FLUXGRAPH_ROOT}" fluxgraph)

if(NOT TARGET fluxgraph)
  message(FATAL_ERROR "add_subdirectory did not define the fluxgraph target")
endif()

if(FLUXGRAPH_BUILD_TESTS OR FLUXGRAPH_BUILD_EXAMPLES OR TARGET fluxgraph_tests)
  message(FATAL_ERROR
    "fluxgraph as a subproject defaulted tests or examples on: "
    "FLUXGRAPH_BUILD_TESTS=${FLUXGRAPH_BUILD_TESTS} "
    "FLUXGRAPH_BUILD_EXAMPLES=${FLUXGRAPH_BUILD_EXAMPLES}"
  )
endif()
